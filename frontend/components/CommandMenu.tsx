"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Command,
  CommandDialog,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Kbd } from "@/components/ui/kbd";
import { Button } from "@/components/ui/button";
import { Icon } from "./icons";
import { NAV } from "./navigation";

/** Ctrl/⌘+K palette: jump to a page, or hand the typed text to the copilot. */
export function CommandMenu() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const go = (href: string) => {
    setOpen(false);
    setQuery("");
    router.push(href);
  };
  const q = query.trim();

  return (
    <>
      <Button
        variant="outline"
        onClick={() => setOpen(true)}
        className="h-8 justify-start gap-2 bg-card px-2.5 text-muted-foreground shadow-card sm:w-60"
      >
        <Icon name="search" />
        <span className="hidden flex-1 text-left font-normal sm:inline">Search or ask…</span>
        <Kbd className="hidden sm:inline-flex">Ctrl K</Kbd>
      </Button>

      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Command menu"
        description="Go to a page, or ask the copilot."
      >
        {/* shadcn's CommandDialog no longer adds the cmdk root; without it every Command* part
            crashes ("reading 'subscribe'") as soon as the dialog opens. */}
        <Command>
          <CommandInput
            placeholder="Go to a page, or type a question…"
            value={query}
            onValueChange={setQuery}
          />
          <CommandList>
            {NAV.map((group) => (
              <CommandGroup key={group.group} heading={group.group}>
                {group.items.map((item) => (
                  <CommandItem
                    key={item.href}
                    value={`${item.label} ${item.hint}`}
                    onSelect={() => go(item.href)}
                  >
                    <Icon name={item.icon} />
                    <span>{item.label}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{item.hint}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
            {/* After the pages, so "Search lab" + Enter opens the page; always mounted, so any
                text that matches no page can still be asked. */}
            {q && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Ask" forceMount>
                  <CommandItem
                    forceMount
                    value="ask-the-copilot"
                    onSelect={() => go(`/copilot?q=${encodeURIComponent(q)}`)}
                  >
                    <Icon name="chat" />
                    Ask the copilot: “{q}”
                  </CommandItem>
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </CommandDialog>
    </>
  );
}
