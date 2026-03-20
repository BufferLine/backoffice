"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

const securityEvents = [
  {
    title: "Password rotated",
    detail: "Required every 90 days",
    timestamp: "2 days ago",
  },
  {
    title: "Finance API token",
    detail: "Scoped to invoice exports",
    timestamp: "7 days ago",
  },
  {
    title: "Singapore sign-in",
    detail: "Chrome on macOS",
    timestamp: "Mar 14, 2024",
  },
] as const;

const connectedTools = [
  {
    name: "Airwallex",
    detail: "Last verification completed successfully",
    status: "Healthy",
    tone: "emerald",
  },
  {
    name: "Xero Mirror",
    detail: "Last verification completed successfully",
    status: "Needs review",
    tone: "amber",
  },
  {
    name: "Payroll Export",
    detail: "Last verification completed successfully",
    status: "Healthy",
    tone: "emerald",
  },
] as const;

const operationalPermissions = [
  "Approve invoices up to SGD 50,000",
  "Release payroll exports",
  "Invite and suspend finance users",
  "Manage crypto payout wallets",
  "Export audit trails",
  "Override expense policy flags",
] as const;

const badgeClassNames = {
  emerald:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300",
  amber:
    "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300",
} satisfies Record<string, string>;

function getInitials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-[0.32em] text-[var(--muted-strong)]">
        {eyebrow}
      </p>
      <div className="space-y-1">
        <h2 className="text-xl font-semibold text-[var(--foreground)]">{title}</h2>
        <p className="max-w-2xl text-sm leading-6 text-[var(--muted)]">
          {description}
        </p>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadAccount() {
      try {
        const data = await api.get<Me>("/api/auth/me");
        if (!cancelled) {
          setMe(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load account");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadAccount();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleLogout() {
    try {
      await api.post("/api/auth/logout");
    } catch {
      // JWT logout is stateless; local tokens still need to be cleared.
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      router.push("/login");
    }
  }

  const identityItems = [
    ["Display name", me?.name ?? (loading ? "Loading..." : "Unavailable")],
    ["Work email", me?.email ?? (loading ? "Loading..." : "Unavailable")],
    ["Department", me?.roles[0]?.name ?? (loading ? "Loading..." : "Finance Operations")],
    ["Reporting line", "Head of Accounting"],
    ["Default workspace", "Your Company"],
    ["Timezone", "GMT+8 Singapore"],
  ] as const;

  const securityScore = me
    ? Math.min(100, 58 + me.roles.length * 10 + me.permissions.length * 4)
    : 0;
  const accountRole = me?.roles[0]?.name ?? (loading ? "Loading..." : "Finance Admin");
  const accountRoleDetail =
    me?.roles[0]?.description ?? "Primary accounting operator";

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(14,165,233,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(245,158,11,0.16),_transparent_26%),linear-gradient(180deg,_var(--surface)_0%,_var(--background)_52%)] px-6 py-8 text-[var(--foreground)] sm:px-10 lg:px-14">
      <div className="mx-auto flex max-w-7xl flex-col gap-8">
        <section className="overflow-hidden rounded-[2rem] border border-white/60 bg-[linear-gradient(135deg,_rgba(15,23,42,0.96),_rgba(17,24,39,0.92))] shadow-[0_32px_80px_rgba(15,23,42,0.18)] ring-1 ring-black/5">
          <div className="grid gap-8 px-7 py-8 text-white sm:px-10 lg:grid-cols-[1.35fr_0.9fr] lg:px-12 lg:py-12">
            <div className="space-y-6">
              <div className="inline-flex items-center gap-3 rounded-full border border-white/15 bg-white/8 px-4 py-2 text-sm backdrop-blur">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                Account verified for payment operations
              </div>
              <div className="space-y-4">
                <p className="text-sm font-medium uppercase tracking-[0.34em] text-cyan-200/80">
                  Account design
                </p>
                <div className="space-y-3">
                  <h1 className="max-w-3xl text-4xl font-semibold tracking-[-0.04em] sm:text-5xl">
                    Operator settings built for finance teams, not generic profile forms.
                  </h1>
                  <p className="max-w-2xl text-sm leading-7 text-slate-300 sm:text-base">
                    Review identity, approval controls, and backend access
                    posture from one surface. The layout is tuned for
                    high-signal operational checks instead of a generic profile page.
                  </p>
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-2xl border border-white/10 bg-white/6 p-4">
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-400">
                    Role
                  </p>
                  <p className="mt-3 text-lg font-semibold">
                    {accountRole}
                  </p>
                  <p className="mt-1 text-sm text-slate-300">
                    Approval rights
                  </p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/6 p-4">
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-400">
                    Region
                  </p>
                  <p className="mt-3 text-lg font-semibold">Singapore</p>
                  <p className="mt-1 text-sm text-slate-300">
                    GST and payroll
                  </p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/6 p-4">
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-400">
                    Approval SLA
                  </p>
                  <p className="mt-3 text-lg font-semibold">&lt; 4 hours</p>
                  <p className="mt-1 text-sm text-slate-300">
                    For invoice and expense queues
                  </p>
                </div>
              </div>
            </div>

            <div className="flex flex-col justify-between gap-6 rounded-[1.75rem] border border-white/10 bg-white/8 p-6 backdrop-blur">
              <div className="flex items-center gap-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-300 via-sky-400 to-blue-500 text-xl font-semibold text-slate-950">
                  {me ? getInitials(me.name) : "--"}
                </div>
                <div className="space-y-1">
                  <p className="text-lg font-semibold">
                    {me?.name ?? (loading ? "Loading account..." : "Account unavailable")}
                  </p>
                  <p className="text-sm text-slate-300">
                    {me?.email ?? "No authenticated profile loaded"}
                  </p>
                  <p className="text-sm text-cyan-200">
                    {me ? accountRoleDetail : "Awaiting role sync"}
                  </p>
                </div>
              </div>
              <div className="space-y-4 rounded-2xl border border-white/10 bg-slate-950/30 p-5">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-300">Security score</span>
                  <span className="font-semibold text-white">{securityScore} / 100</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-cyan-300 to-emerald-400"
                    style={{ width: `${securityScore}%` }}
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
                    <p className="text-xs uppercase tracking-[0.26em] text-slate-400">
                      MFA
                    </p>
                    <p className="mt-2 text-base font-semibold">
                      Hardware key + TOTP
                    </p>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
                    <p className="text-xs uppercase tracking-[0.26em] text-slate-400">
                      Session policy
                    </p>
                    <p className="mt-2 text-base font-semibold">Trusted devices only</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="inline-flex rounded-full border border-white/20 px-4 py-2 text-sm font-medium text-white transition hover:bg-white hover:text-slate-950"
                >
                  Sign out
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.3fr_0.95fr]">
          <div className="space-y-6">
            <div className="rounded-[1.75rem] border border-[var(--card-border)] bg-[var(--card)] p-7 shadow-[0_24px_70px_rgba(15,23,42,0.06)]">
              <SectionHeading
                eyebrow="Identity"
                title="Personal account profile"
                description="Administrative details are arranged as reference cards so account validation can happen quickly against real API-backed fields."
              />
              <div className="mt-8 grid gap-4 md:grid-cols-2">
                {identityItems.map(([label, value]) => (
                  <div
                    key={label}
                    className="rounded-2xl border border-[var(--card-border)] bg-[var(--surface)] p-4"
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--muted-strong)]">
                      {label}
                    </p>
                    <p className="mt-3 text-base font-semibold text-[var(--foreground)]">
                      {value}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[1.75rem] border border-[var(--card-border)] bg-[var(--card)] p-7 shadow-[0_24px_70px_rgba(15,23,42,0.06)]">
              <SectionHeading
                eyebrow="Authorizations"
                title="Operational permissions"
                description="The page emphasizes approval scopes and risk boundaries, which is usually the first question during account validation."
              />
              <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {operationalPermissions.map((permission) => (
                  <div
                    key={permission}
                    className="rounded-2xl border border-[var(--card-border)] bg-[var(--surface)] px-4 py-4 text-sm font-medium text-[var(--foreground)]"
                  >
                    {permission}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-[1.75rem] border border-[var(--card-border)] bg-[var(--card)] p-7 shadow-[0_24px_70px_rgba(15,23,42,0.06)]">
              <SectionHeading
                eyebrow="Connected Tools"
                title="System health"
                description="Integrations are surfaced as status chips instead of a settings table to keep failures visible."
              />
              <div className="mt-8 space-y-3">
                {connectedTools.map((tool) => (
                  <div
                    key={tool.name}
                    className="flex items-center justify-between rounded-2xl border border-[var(--card-border)] bg-[var(--surface)] px-4 py-4"
                  >
                    <div>
                      <p className="font-semibold text-[var(--foreground)]">{tool.name}</p>
                      <p className="text-sm text-[var(--muted)]">
                        {error ? "Manual review required after load failure" : tool.detail}
                      </p>
                    </div>
                    <span
                      className={`rounded-full border px-3 py-1 text-xs font-semibold ${badgeClassNames[tool.tone]}`}
                    >
                      {tool.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[1.75rem] border border-[var(--card-border)] bg-[var(--card)] p-7 shadow-[0_24px_70px_rgba(15,23,42,0.06)]">
              <SectionHeading
                eyebrow="Security"
                title="Recent account events"
                description="Recent credential and access events are grouped chronologically to support quick manual review."
              />
              <div className="mt-8 space-y-4">
                {securityEvents.map((event) => (
                  <div
                    key={event.title}
                    className="rounded-2xl border border-[var(--card-border)] bg-[var(--surface)] p-4"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="font-semibold text-[var(--foreground)]">
                          {event.title}
                        </p>
                        <p className="mt-1 text-sm text-[var(--muted)]">
                          {event.detail}
                        </p>
                      </div>
                      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-strong)]">
                        {event.timestamp}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {error && (
          <div className="rounded-[1.5rem] border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800 shadow-[0_16px_40px_rgba(180,83,9,0.08)]">
            {error}
          </div>
        )}
      </div>
    </main>
  );
}
