import axios, { AxiosError } from "axios";
import { useAuthStore } from "./store";

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
  // El refresh token viaja como cookie httpOnly bajo el path /auth; el
  // backend la lee solo, el frontend nunca accede a su valor.
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  try {
    const response = await axios.post(
      `${process.env.NEXT_PUBLIC_API_URL}/auth/refresh`,
      null,
      { withCredentials: true }
    );
    const newToken: string = response.data?.data?.access_token;
    if (newToken) {
      useAuthStore.getState().setSession(newToken, useAuthStore.getState().user);
      return newToken;
    }
    return null;
  } catch {
    return null;
  }
}

// En estas rutas un 401 significa "credenciales incorrectas", no "sesion vencida":
// el error debe llegar al componente para mostrarse sin recargar la pagina.
const AUTH_ROUTES_WITHOUT_REFRESH = ["/auth/login", "/auth/register", "/auth/refresh"];

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as (typeof error.config & { _retried?: boolean }) | undefined;
    const status = error.response?.status;
    const isAuthRoute = AUTH_ROUTES_WITHOUT_REFRESH.some((route) => originalRequest?.url?.includes(route));

    if (status === 401 && originalRequest && !originalRequest._retried && !isAuthRoute) {
      originalRequest._retried = true;

      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      const newToken = await refreshPromise;

      if (newToken) {
        originalRequest.headers = originalRequest.headers ?? {};
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      }

      useAuthStore.getState().clearSession();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }

    return Promise.reject(error);
  }
);
