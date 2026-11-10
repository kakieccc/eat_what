import { CloudOff, RotateCw } from "lucide-react";
import { useLocation } from "react-router-dom";
import { Button } from "../components/ui/button";
import { returnPath } from "../lib/utils";

export function ServiceError() {
  const location = useLocation();
  return (
    <section className="service-error" role="alert">
      <div className="service-error-icon"><CloudOff aria-hidden="true" /></div>
      <h1>服务暂时不可用</h1>
      <p>暂时无法完成请求，请稍后重新连接。</p>
      <Button onClick={() => window.location.replace(window.location.origin + returnPath(location.state))}>
        <RotateCw data-icon="inline-start" />重新连接
      </Button>
    </section>
  );
}
