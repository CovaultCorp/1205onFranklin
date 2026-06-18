import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "ENTRY POINT | Sign In",
  description: "Building access and tenant management for 1205 on Franklin"
};

export default function LoginLayout({ children }: { children: ReactNode }) {
  return children;
}
