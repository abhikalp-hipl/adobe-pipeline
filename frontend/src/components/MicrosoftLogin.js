import React from "react";

function MicrosoftLogin() {
  const handleLogin = () => {
    const clientId = process.env.REACT_APP_MS_CLIENT_ID;
    if (!clientId) {
      // Keep this explicit so we do not accidentally use a wrong app/tenant.
      // eslint-disable-next-line no-alert
      alert("Missing REACT_APP_MS_CLIENT_ID in frontend environment.");
      return;
    }
    const redirectUri = encodeURIComponent("http://localhost:8000/auth/callback");
    const scope = encodeURIComponent("openid profile email offline_access Files.ReadWrite.All User.Read");
    const state = window.crypto?.randomUUID?.() || `${Date.now()}-oauth`;
    document.cookie = `ms_oauth_state=${encodeURIComponent(state)}; path=/; max-age=600; samesite=lax`;

    const loginUrl =
      "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" +
      `client_id=${encodeURIComponent(clientId)}` +
      "&response_type=code" +
      `&redirect_uri=${redirectUri}` +
      "&response_mode=query" +
      `&scope=${scope}` +
      `&state=${encodeURIComponent(state)}`;

    // Debug final authorize URL to validate tenant/client/redirect consistency.
    // eslint-disable-next-line no-console
    console.log(loginUrl);
    window.location.href = loginUrl;
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
