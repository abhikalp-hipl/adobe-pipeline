import React, { useEffect, useState } from "react";

import Login from "./pages/Login";
import AdminPanel from "./pages/AdminPanel";
import Dashboard from "./pages/Dashboard";
import { getAppJwt, parseJwtPayload } from "./services/api";

function usePathname() {
  const [pathname, setPathname] = useState(() =>
    typeof window !== "undefined" ? window.location.pathname : "/login"
  );

  useEffect(() => {
    const sync = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  useEffect(() => {
    if (pathname !== "/" || typeof window === "undefined") return;
    const token = getAppJwt();
    const payload = parseJwtPayload(token);
    const dest = !token ? "/login" : payload?.role === "super_admin" ? "/admin" : "/dashboard";
    window.history.replaceState({}, "", dest);
    setPathname(dest);
  }, [pathname]);

  return pathname;
}

function Redirecting({ to }) {
  useEffect(() => {
    window.location.replace(to);
  }, [to]);
  return (
    <div className="h-screen flex items-center justify-center bg-gray-100">
      <div className="text-gray-600 text-sm">Redirecting…</div>
    </div>
  );
}

export default function App() {
  const pathname = usePathname();
  const token = getAppJwt();
  const payload = parseJwtPayload(token);

  if (pathname === "/login") {
    return <Login />;
  }

  if (!token) {
    return <Redirecting to="/login" />;
  }

  if (pathname === "/admin") {
    if (payload?.role !== "super_admin") {
      return <Redirecting to="/login" />;
    }
    return <AdminPanel />;
  }

  if (pathname === "/dept-settings") {
    if (payload?.role !== "dept_user") {
      return <Redirecting to="/login" />;
    }
    return <Dashboard initialActivePage="dept-settings" />;
  }

  if (pathname === "/dashboard") {
    if (payload?.role === "super_admin") {
      return <Redirecting to="/admin" />;
    }
    if (payload?.role !== "dept_user") {
      return <Redirecting to="/login" />;
    }
    return <Dashboard />;
  }

  const fallback =
    payload?.role === "super_admin" ? "/admin" : payload?.role === "dept_user" ? "/dashboard" : "/login";
  return <Redirecting to={fallback} />;
}
