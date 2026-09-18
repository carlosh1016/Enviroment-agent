"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { useHydrated } from "@/lib/hooks/use-hydrated";

export default function RootPage() {
  const router = useRouter();
  const hydrated = useHydrated();
  const accessToken = useAuthStore((state) => state.accessToken);

  useEffect(() => {
    if (!hydrated) return;
    router.replace(accessToken ? "/dashboard" : "/login");
  }, [hydrated, accessToken, router]);

  return null;
}
