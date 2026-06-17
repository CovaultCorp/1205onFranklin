"use client";

import { Button, Tooltip } from "@nextui-org/react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";

  return (
    <Tooltip content="Toggle theme">
      <Button isIconOnly variant="flat" onPress={() => setTheme(isDark ? "light" : "dark")}>
        {isDark ? <Sun size={18} /> : <Moon size={18} />}
      </Button>
    </Tooltip>
  );
}
