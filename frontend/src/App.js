import React, { useEffect, useState } from "react";

import MicrosoftLogin from "./components/MicrosoftLogin";
import Dashboard from "./pages/Dashboard";
import { getAuthStatus } from "./services/api";

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchAuthStatus = async () => {
      try {
        const status = await getAuthStatus();
        setIsAuthenticated(Boolean(status?.authenticated));
      } catch {
        setIsAuthenticated(false);
      } finally {
        setIsLoading(false);
      }
    };
    fetchAuthStatus();
  }, []);

  useEffect(() => {
    if (isLoading) {
      return;
    }
    if (isAuthenticated && window.location.pathname !== "/dashboard") {
      window.history.replaceState({}, "", "/dashboard");
    }
    if (!isAuthenticated && window.location.pathname !== "/") {
      window.history.replaceState({}, "", "/");
    }
  }, [isAuthenticated, isLoading]);

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-100">
        <div className="text-gray-600">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-100">
        <MicrosoftLogin />
      </div>
    );
  }

  return (
    <Dashboard />
  );
}

export default App;
