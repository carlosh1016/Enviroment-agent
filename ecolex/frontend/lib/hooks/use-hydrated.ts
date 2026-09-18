"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store";

/**
 * zustand/persist rehidrata el store desde localStorage de forma asincrona
 * despues del primer render. Sin esto, un guard que lee accessToken en un
 * useEffect de montaje puede ver `null` y redirigir a /login antes de que
 * la rehidratacion termine (se manifiesta en cualquier recarga completa de
 * pagina, ej. F5 en /documents ya autenticado).
 *
 * El acceso a `useAuthStore.persist` vive solo dentro de useEffect (nunca en
 * el render ni en el inicializador de useState) porque durante el build de
 * Next (prerender de paginas "use client") ese objeto no existe todavia.
 */
export function useHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (useAuthStore.persist.hasHydrated()) {
      setHydrated(true);
      return;
    }
    const unsub = useAuthStore.persist.onFinishHydration(() => setHydrated(true));
    return unsub;
  }, []);

  return hydrated;
}
