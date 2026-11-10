import { Link, NavLink, useLocation } from "react-router-dom";
import { Clock, SlidersHorizontal, UserRound, Utensils } from "lucide-react";
import { useAuth } from "../lib/auth";
import { Brand } from "./brand";

function useHomeSection() {
  const { pathname } = useLocation();
  return ["/", "/map", "/discover"].includes(pathname) || pathname.startsWith("/decision-runs/");
}

export function MobileNavigation() {
  const home = useHomeSection();
  return <nav className="bottom-nav" aria-label="主导航">
    <Link to="/" className={home ? "active" : undefined} aria-current={home ? "page" : undefined}>
      <Utensils size={24} aria-hidden="true" /><span>首页</span>
    </Link>
    <NavLink to="/history"><Clock size={24} aria-hidden="true" /><span>历史</span></NavLink>
    <NavLink to="/profile"><SlidersHorizontal size={24} aria-hidden="true" /><span>偏好</span></NavLink>
  </nav>;
}

export function DesktopNavigation() {
  const home = useHomeSection();
  const { user } = useAuth();
  return <aside className="desktop-sidebar">
    <Link to="/" aria-label="今天吃什么首页"><Brand /></Link>
    <nav aria-label="主导航">
      <Link to="/" className={home ? "active" : undefined} aria-current={home ? "page" : undefined}>
        <Utensils size={20} aria-hidden="true" /><span>开始选餐</span>
      </Link>
      <NavLink to="/history"><Clock size={20} aria-hidden="true" /><span>用餐历史</span></NavLink>
      <NavLink to="/profile"><SlidersHorizontal size={20} aria-hidden="true" /><span>用餐偏好</span></NavLink>
    </nav>
    <Link to="/profile" className="desktop-account">
      <UserRound size={24} aria-hidden="true" /><span>{user?.displayName}</span>
    </Link>
  </aside>;
}
