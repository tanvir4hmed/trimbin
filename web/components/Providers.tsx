"use client";

/**
 * The one cache, mounted once.
 *
 * Created in state rather than at module scope: a module-level client is shared
 * by every request the Next server handles, so one visitor's dashboard could be
 * served to the next. In the browser it makes no difference; on the server it is
 * a data leak, and the difference is invisible until it happens.
 */

import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { makeQueryClient } from "@/lib/queries";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(makeQueryClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
