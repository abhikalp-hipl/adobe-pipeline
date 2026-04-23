import React from "react";

function MicrosoftLogin() {
  const handleLogin = () => {
    // Always initiate OAuth from backend so it owns state generation/validation.
    window.location.href = "http://localhost:8000/auth/login";
  };

  return (
    <div className="bg-white p-6 rounded-xl shadow w-80 text-center">
      <h2 className="text-xl font-semibold mb-4">Microsoft Authentication</h2>
      <button
        type="button"
        onClick={handleLogin}
        className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
      >
        Login with Microsoft
      </button>
      <p className="mt-2 text-sm text-slate-600">
        After successful login, you will be redirected back to the dashboard.
      </p>
    </div>
  );
}

export default MicrosoftLogin;
