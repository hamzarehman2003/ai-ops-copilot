"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setApiUser, type UserOption, type Me } from "@/lib/api";
import { DEFAULT_USER } from "@/lib/roles";

const STORAGE_KEY = "copilot.user";

interface UserContextValue {
  email: string;
  users: UserOption[];
  me: Me | null;
  meError: unknown;
  setEmail: (email: string) => void;
}

const UserContext = createContext<UserContextValue | null>(null);

function readStoredEmail(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_USER;
  } catch {
    return DEFAULT_USER;
  }
}

/**
 * "Signed in as" stand-in for auth: the chosen user's email is sent as `X-User` on every
 * request. Children are keyed by email so every page remounts (fresh state) on a switch.
 */
export function UserProvider({ children }: { children: ReactNode }) {
  const [email, setEmailState] = useState<string | null>(null);
  const [users, setUsers] = useState<UserOption[]>([]);
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<unknown>(null);

  const setEmail = useCallback((next: string) => {
    setApiUser(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode: the choice just isn't remembered */
    }
    setEmailState(next);
  }, []);

  useEffect(() => {
    setEmail(readStoredEmail());
    api
      .users()
      .then(setUsers)
      .catch(() => setUsers([]));
  }, [setEmail]);

  useEffect(() => {
    if (!email) return;
    let cancelled = false;
    setMe(null);
    setMeError(null);
    api
      .me()
      .then((m) => !cancelled && setMe(m))
      .catch((e) => {
        if (cancelled) return;
        setMeError(e);
        // A stale/unknown email in localStorage: fall back to the default user.
        if (email !== DEFAULT_USER && (e as { status?: number }).status === 401) {
          setEmail(DEFAULT_USER);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [email, setEmail]);

  if (!email) return null;
  return (
    <UserContext.Provider value={{ email, users, me, meError, setEmail }}>
      <div key={email} className="contents">
        {children}
      </div>
    </UserContext.Provider>
  );
}

export function useUser(): UserContextValue {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error("useUser must be used inside <UserProvider>");
  return ctx;
}

/** Role of the signed-in user (undefined while /api/me is loading). */
export function useRole() {
  return useUser().me?.user.role;
}
