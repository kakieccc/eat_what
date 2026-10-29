import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.service.runner import DecisionRunner
from app.modules.decision.workflow.context import execution_deadline
from app.modules.decision.workflow.state import SCHEMA_VERSION
from app.modules.location.schemas import Origin
from app.modules.task.errors import LostTaskLease
from app.modules.task.service import TaskWorker
from app.modules.task.types import TaskClaim


class TaskConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_only_stops_its_own_execution(self):
        await self.assert_failure_isolated(False)

    async def test_lost_lease_only_stops_its_own_execution(self):
        await self.assert_failure_isolated(True)

    async def assert_failure_isolated(self, lost_lease):
        claims = [TaskClaim(name, name + "-token") for name in ("bad", "good", "next")]
        active = set()
        good_started, next_started = asyncio.Event(), asyncio.Event()

        async def claim(_):
            return claims.pop(0) if claims else None

        async def renew(claim, _):
            if lost_lease and claim.task_id == "bad":
                raise LostTaskLease("lease expired")

        async def execute(claim):
            active.add(claim.task_id)
            if claim.task_id == "good":
                good_started.set()
            if claim.task_id == "next":
                next_started.set()
            try:
                if claim.task_id == "bad" and not lost_lease:
                    await good_started.wait()
                    raise RuntimeError("one task failed")
                await asyncio.Future()
            finally:
                active.remove(claim.task_id)

        handler = SimpleNamespace(execute_claim=execute, fail=AsyncMock())
        store = SimpleNamespace(claim=claim, renew=renew)
        worker = TaskWorker(store, handler, lease_seconds=3, poll_seconds=0.01, concurrency=2)
        running = asyncio.create_task(worker.run())
        try:
            await asyncio.wait_for(next_started.wait(), timeout=5)
            self.assertEqual(active, {"good", "next"})
            self.assertEqual(handler.fail.await_count, 0 if lost_lease else 1)
            if not lost_lease:
                self.assertEqual(handler.fail.await_args.args[0].task_id, "bad")
        finally:
            running.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await running
        self.assertFalse(active)

    async def test_shared_graph_keeps_each_tasks_state_events_and_deadline_isolated(self):
        arrived, deadlines = set(), {}
        both_arrived = asyncio.Event()

        async def search(state):
            task_id = state["task_id"]
            deadlines[task_id] = execution_deadline.get()
            arrived.add(task_id)
            if len(arrived) == 2:
                both_arrived.set()
            await both_arrived.wait()
            self.assertEqual(execution_deadline.get(), deadlines[task_id])
            self.assertEqual(state["request"]["request_text"], task_id)
            return {"places": [], "filter_summary": {}}

        async def filter_places(_):
            return {"places": []}

        async def prepare(claim):
            request = DecisionRequest(origin=Origin(latitude=31.23, longitude=121.47), request_text=claim.task_id)
            state = {"schema_version": SCHEMA_VERSION, "task_id": claim.task_id,
                     "lease_token": claim.lease_token, "decision_run_id": "run-" + claim.task_id,
                     "request": request.model_dump(mode="json")}
            return claim.task_id, "run-" + claim.task_id, "request-" + claim.task_id, state, 0

        repository = SimpleNamespace(prepare=prepare, complete=AsyncMock())
        tasks = SimpleNamespace(append_event=AsyncMock(), start_step=AsyncMock(), complete_step=AsyncMock())
        with patch("app.modules.decision.workflow.graph.search_places.build", return_value=search), \
                patch("app.modules.decision.workflow.graph.filter_places.build", return_value=filter_places):
            runner = DecisionRunner(repository, tasks, None, None, timeout_seconds=3)
        token = execution_deadline.set(123)
        try:
            await asyncio.wait_for(asyncio.gather(*(
                runner.execute_claim(TaskClaim(name, name + "-token")) for name in ("alpha", "beta")
            )), timeout=5)
            self.assertEqual(execution_deadline.get(), 123)
        finally:
            execution_deadline.reset(token)
        self.assertEqual(arrived, {"alpha", "beta"})
        self.assertTrue(all(deadline > 123 for deadline in deadlines.values()))
        self.assertEqual(repository.complete.await_count, 2)
        for call in repository.complete.await_args_list:
            claim, state, run_id, _ = call.args
            self.assertEqual(state["task_id"], claim.task_id)
            self.assertEqual(state["request"]["request_text"], claim.task_id)
            self.assertEqual(state["decision_run_id"], run_id)
        self.assertEqual({call.args[0].task_id for call in tasks.append_event.await_args_list}, {"alpha", "beta"})
        for task_id in ("alpha", "beta"):
            events = [call.args[1].type for call in tasks.append_event.await_args_list
                      if call.args[0].task_id == task_id]
            self.assertEqual(events, ["runStarted", "nodeStarted", "nodeCompleted", "nodeStarted", "nodeCompleted"])


if __name__ == "__main__":
    unittest.main()
