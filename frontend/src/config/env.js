export const MS_CLIENT_ID = import.meta.env.VITE_MS_CLIENT_ID || "";
export const MS_TENANT_ID = import.meta.env.VITE_MS_TENANT_ID || "";

export const isMicrosoftConfigReady = Boolean(MS_CLIENT_ID && MS_TENANT_ID);
