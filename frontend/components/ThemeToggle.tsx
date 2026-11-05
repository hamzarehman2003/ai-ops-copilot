"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Icon } from "./icons";

/** Light / dark / system, remembered by next-themes. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const current = mounted ? (theme ?? "system") : "system";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Theme" className="text-muted-foreground">
          <Icon name={current === "dark" ? "moon" : current === "light" ? "sun" : "monitor"} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="end" className="min-w-36">
        <DropdownMenuRadioGroup value={current} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light">
            <Icon name="sun" /> Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Icon name="moon" /> Dark
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Icon name="monitor" /> System
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
