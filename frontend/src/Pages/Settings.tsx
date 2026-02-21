import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type AppSettings = {
  workspace_identity: {
    default_project: string;
    timezone: string;
    date_format: string;
    display_name: string;
    email: string;
    role: string;
    team_owner_map: Record<string, string>;
    show_rules_created_by_others: boolean;
  };
  rule_engine_defaults: {
    default_severity: string;
    auto_approve_confidence: number;
    duplicate_similarity_threshold: number;
    default_pack_by_rule_type: Record<string, string>;
  };
  validation_scan_behavior: {
    auto_scan_on_upload: boolean;
    max_rules_per_extraction: number;
    validation_mode: string;
    ignore_patterns: string[];
  };
  ai_assistant_controls: {
    provider: string;
    model: string;
    model_api_key?: string;
    model_api_key_masked?: string;
    has_model_api_key?: boolean;
    prompt_style: string;
    max_tokens: number;
    response_length: string;
    log_suggestions: boolean;
    allow_llm_fallback: boolean;
  };
  dashboard_preferences: {
    default_date_range_days: number;
    default_grouping: string;
    kpi_cards: {
      open_violations: boolean;
      fixed_rate: boolean;
      top_rule_packs: boolean;
      active_developers: boolean;
    };
    auto_refresh_interval_sec: number;
  };
  notifications: {
    channels: string[];
    triggers: string[];
    digest_frequency: string;
  };
  security_compliance: {
    retention_days: number;
    pii_masking: boolean;
    audit_log_export: boolean;
    settings_change_roles: string[];
  };
  integrations: {
    sap_endpoint: string;
    ticketing_provider: string;
    ci_hook_url: string;
    webhook_secret: string;
  };
};

const defaultSettings: AppSettings = {
  workspace_identity: {
    default_project: "",
    timezone: "UTC",
    date_format: "YYYY-MM-DD",
    display_name: "",
    email: "name@zalaris.com",
    role: "developer",
    team_owner_map: {},
    show_rules_created_by_others: true,
  },
  rule_engine_defaults: {
    default_severity: "WARNING",
    auto_approve_confidence: 0.85,
    duplicate_similarity_threshold: 0.9,
    default_pack_by_rule_type: {},
  },
  validation_scan_behavior: {
    auto_scan_on_upload: true,
    max_rules_per_extraction: 10,
    validation_mode: "strict",
    ignore_patterns: [],
  },
  ai_assistant_controls: {
    provider: "openai",
    model: "gpt-4.1-mini",
    model_api_key: "",
    model_api_key_masked: "",
    has_model_api_key: false,
    prompt_style: "balanced",
    max_tokens: 1200,
    response_length: "medium",
    log_suggestions: true,
    allow_llm_fallback: false,
  },
  dashboard_preferences: {
    default_date_range_days: 30,
    default_grouping: "developer",
    kpi_cards: {
      open_violations: true,
      fixed_rate: true,
      top_rule_packs: true,
      active_developers: true,
    },
    auto_refresh_interval_sec: 0,
  },
  notifications: {
    channels: ["email"],
    triggers: ["new_high_severity", "failed_validation"],
    digest_frequency: "daily",
  },
  security_compliance: {
    retention_days: 180,
    pii_masking: true,
    audit_log_export: true,
    settings_change_roles: ["admin"],
  },
  integrations: {
    sap_endpoint: "",
    ticketing_provider: "",
    ci_hook_url: "",
    webhook_secret: "",
  },
};

function csvToArray(value: string): string[] {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function arrayToCsv(value: string[]): string {
  return value.join(", ");
}

function textToMap(value: string): Record<string, string> {
  const out: Record<string, string> = {};
  value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const idx = line.indexOf("=");
      if (idx <= 0) return;
      const key = line.slice(0, idx).trim();
      const val = line.slice(idx + 1).trim();
      if (key) out[key] = val;
    });
  return out;
}

function mapToText(value: Record<string, string>): string {
  return Object.entries(value)
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");
}

type SettingsProps = {
  themeName?: string;
  onThemeChange?: (value: string) => void;
};
type SettingsTab = "workspace" | "rules" | "ai" | "dashboard" | "ops";

type LlmUsagePoint = {
  date: string;
  cost_eur: number;
  calls: number;
  total_tokens: number;
};

type LlmUsageDailyResponse = {
  days: number;
  currency: string;
  total_cost_eur: number;
  total_calls: number;
  series: LlmUsagePoint[];
};

export default function Settings({ themeName, onThemeChange }: SettingsProps) {
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clearingViolations, setClearingViolations] = useState(false);
  const [modelApiKeyInput, setModelApiKeyInput] = useState("");
  const [showModelApiKey, setShowModelApiKey] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [llmDays, setLlmDays] = useState(30);
  const [llmUsage, setLlmUsage] = useState<LlmUsageDailyResponse>({
    days: 30,
    currency: "EUR",
    total_cost_eur: 0,
    total_calls: 0,
    series: [],
  });
  const [llmUsageLoading, setLlmUsageLoading] = useState(false);
  const [llmUsageError, setLlmUsageError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>("workspace");

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const res = await fetch("/api/settings");
        if (!res.ok) throw new Error(await res.text());
        const data = (await res.json()) as AppSettings;
        setSettings({ ...defaultSettings, ...data });
        setModelApiKeyInput("");
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to load settings");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  useEffect(() => {
    const loadLlmUsage = async () => {
      try {
        setLlmUsageLoading(true);
        setLlmUsageError(null);
        const res = await fetch(`/api/settings/llm-usage/daily-cost?days=${llmDays}`);
        if (!res.ok) throw new Error(await res.text());
        const data = (await res.json()) as LlmUsageDailyResponse;
        setLlmUsage(data);
      } catch (err: unknown) {
        setLlmUsageError(err instanceof Error ? err.message : "Failed to load LLM usage.");
      } finally {
        setLlmUsageLoading(false);
      }
    };
    void loadLlmUsage();
  }, [llmDays]);

  async function saveSettings() {
    try {
      setSaving(true);
      setMessage(null);
      setError(null);
      const payload: AppSettings = {
        ...settings,
        ai_assistant_controls: {
          ...settings.ai_assistant_controls,
        },
      };
      delete payload.ai_assistant_controls.model_api_key_masked;
      delete payload.ai_assistant_controls.has_model_api_key;
      if (modelApiKeyInput.trim()) {
        payload.ai_assistant_controls.model_api_key = modelApiKeyInput.trim();
      } else {
        delete payload.ai_assistant_controls.model_api_key;
      }
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = (await res.json()) as AppSettings;
      setSettings(updated);
      setModelApiKeyInput("");
      setMessage("Settings saved.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  async function clearFixedViolations() {
    try {
      setError(null);
      setMessage(null);
      setClearingViolations(true);
      const res = await fetch("/api/dashboard/violations/clear-fixed", {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as { deleted: number };
      setMessage(`Deleted ${data.deleted} fixed violation(s).`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to clear fixed violations");
    } finally {
      setClearingViolations(false);
    }
  }

  if (loading) {
    return <div className="p-6 text-sm text-gray-600">Loading settings...</div>;
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-indigo-700">Settings</h2>
          <p className="mt-1 text-sm text-gray-600">Enterprise configuration for governance, AI, and operations.</p>
        </div>
        <button
          onClick={saveSettings}
          disabled={saving}
          className="rounded bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700 disabled:opacity-60"
        >
          {saving ? "Saving..." : "Save All Settings"}
        </button>
      </div>

      {message && <div className="rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div>}
      {error && <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      <div className="rounded-lg border bg-white p-2 shadow-sm">
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setActiveTab("workspace")} className={`rounded px-3 py-2 text-sm ${activeTab === "workspace" ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}>Workspace</button>
          <button type="button" onClick={() => setActiveTab("rules")} className={`rounded px-3 py-2 text-sm ${activeTab === "rules" ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}>Rules</button>
          <button type="button" onClick={() => setActiveTab("ai")} className={`rounded px-3 py-2 text-sm ${activeTab === "ai" ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}>AI</button>
          <button type="button" onClick={() => setActiveTab("dashboard")} className={`rounded px-3 py-2 text-sm ${activeTab === "dashboard" ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}>Dashboard</button>
          <button type="button" onClick={() => setActiveTab("ops")} className={`rounded px-3 py-2 text-sm ${activeTab === "ops" ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}>Notifications & Ops</button>
        </div>
      </div>

      {activeTab === "workspace" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Workspace & Identity</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input className="rounded border px-3 py-2 text-sm" placeholder="Default project" value={settings.workspace_identity.default_project} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, default_project: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Timezone" value={settings.workspace_identity.timezone} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, timezone: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Date format" value={settings.workspace_identity.date_format} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, date_format: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Display name" value={settings.workspace_identity.display_name} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, display_name: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Email" value={settings.workspace_identity.email} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, email: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Role" value={settings.workspace_identity.role} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, role: e.target.value } }))} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.workspace_identity.show_rules_created_by_others}
            onChange={(e) =>
              setSettings((p) => ({
                ...p,
                workspace_identity: {
                  ...p.workspace_identity,
                  show_rules_created_by_others: e.target.checked,
                },
              }))
            }
          />
          Show rules created by other architects/senior developers
        </label>
        <textarea
          className="min-h-20 w-full rounded border px-3 py-2 text-sm"
          placeholder="Team owner map (one per line): developer_email=team_name"
          value={mapToText(settings.workspace_identity.team_owner_map)}
          onChange={(e) =>
            setSettings((p) => ({
              ...p,
              workspace_identity: { ...p.workspace_identity, team_owner_map: textToMap(e.target.value) },
            }))
          }
        />
      </section>}

      {activeTab === "workspace" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Appearance</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <select
            className="rounded border px-3 py-2 text-sm"
            value={themeName || "aurora"}
            onChange={(e) => onThemeChange?.(e.target.value)}
            aria-label="Select color theme"
          >
            <option value="aurora">Aurora Coast</option>
            <option value="sunset">Sunset Sand</option>
            <option value="spruce">Spruce Mint</option>
            <option value="graphite">Graphite Steel</option>
            <option value="citrus">Citrus Grove</option>
            <option value="ocean">Ocean Breeze</option>
          </select>
        </div>
      </section>}

      {activeTab === "rules" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Rule Engine Defaults</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <select className="rounded border px-3 py-2 text-sm" value={settings.rule_engine_defaults.default_severity} onChange={(e) => setSettings((p) => ({ ...p, rule_engine_defaults: { ...p.rule_engine_defaults, default_severity: e.target.value } }))}>
            <option>INFO</option>
            <option>WARNING</option>
            <option>ERROR</option>
          </select>
          <input type="number" step="0.01" min="0" max="1" className="rounded border px-3 py-2 text-sm" value={settings.rule_engine_defaults.auto_approve_confidence} onChange={(e) => setSettings((p) => ({ ...p, rule_engine_defaults: { ...p.rule_engine_defaults, auto_approve_confidence: Number(e.target.value) } }))} />
          <input type="number" step="0.01" min="0" max="1" className="rounded border px-3 py-2 text-sm" value={settings.rule_engine_defaults.duplicate_similarity_threshold} onChange={(e) => setSettings((p) => ({ ...p, rule_engine_defaults: { ...p.rule_engine_defaults, duplicate_similarity_threshold: Number(e.target.value) } }))} />
        </div>
        <textarea
          className="min-h-20 w-full rounded border px-3 py-2 text-sm"
          placeholder="Default pack map (one per line): rule_type=pack_name"
          value={mapToText(settings.rule_engine_defaults.default_pack_by_rule_type)}
          onChange={(e) =>
            setSettings((p) => ({
              ...p,
              rule_engine_defaults: {
                ...p.rule_engine_defaults,
                default_pack_by_rule_type: textToMap(e.target.value),
              },
            }))
          }
        />
      </section>}

      {activeTab === "rules" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Validation & Scan Behavior</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.validation_scan_behavior.auto_scan_on_upload} onChange={(e) => setSettings((p) => ({ ...p, validation_scan_behavior: { ...p.validation_scan_behavior, auto_scan_on_upload: e.target.checked } }))} /> Auto-scan on upload/paste</label>
          <input type="number" min="1" className="rounded border px-3 py-2 text-sm" value={settings.validation_scan_behavior.max_rules_per_extraction} onChange={(e) => setSettings((p) => ({ ...p, validation_scan_behavior: { ...p.validation_scan_behavior, max_rules_per_extraction: Number(e.target.value) } }))} />
          <select className="rounded border px-3 py-2 text-sm" value={settings.validation_scan_behavior.validation_mode} onChange={(e) => setSettings((p) => ({ ...p, validation_scan_behavior: { ...p.validation_scan_behavior, validation_mode: e.target.value } }))}>
            <option value="strict">strict</option>
            <option value="lenient">lenient</option>
          </select>
        </div>
        <input
          className="w-full rounded border px-3 py-2 text-sm"
          placeholder="Ignore patterns (comma-separated)"
          value={arrayToCsv(settings.validation_scan_behavior.ignore_patterns)}
          onChange={(e) =>
            setSettings((p) => ({
              ...p,
              validation_scan_behavior: { ...p.validation_scan_behavior, ignore_patterns: csvToArray(e.target.value) },
            }))
          }
        />
      </section>}

      {activeTab === "ai" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">AI Assistant Controls</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input className="rounded border px-3 py-2 text-sm" placeholder="Provider" value={settings.ai_assistant_controls.provider} onChange={(e) => setSettings((p) => ({ ...p, ai_assistant_controls: { ...p.ai_assistant_controls, provider: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Model" value={settings.ai_assistant_controls.model} onChange={(e) => setSettings((p) => ({ ...p, ai_assistant_controls: { ...p.ai_assistant_controls, model: e.target.value } }))} />
          <select className="rounded border px-3 py-2 text-sm" value={settings.ai_assistant_controls.prompt_style} onChange={(e) => setSettings((p) => ({ ...p, ai_assistant_controls: { ...p.ai_assistant_controls, prompt_style: e.target.value } }))}>
            <option value="strict">strict</option>
            <option value="balanced">balanced</option>
            <option value="concise">concise</option>
          </select>
          <input type="number" min="100" className="rounded border px-3 py-2 text-sm" value={settings.ai_assistant_controls.max_tokens} onChange={(e) => setSettings((p) => ({ ...p, ai_assistant_controls: { ...p.ai_assistant_controls, max_tokens: Number(e.target.value) } }))} />
          <select className="rounded border px-3 py-2 text-sm" value={settings.ai_assistant_controls.response_length} onChange={(e) => setSettings((p) => ({ ...p, ai_assistant_controls: { ...p.ai_assistant_controls, response_length: e.target.value } }))}>
            <option value="short">short</option>
            <option value="medium">medium</option>
            <option value="long">long</option>
          </select>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.ai_assistant_controls.log_suggestions} onChange={(e) => setSettings((p) => ({ ...p, ai_assistant_controls: { ...p.ai_assistant_controls, log_suggestions: e.target.checked } }))} /> Log assistant suggestions</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.ai_assistant_controls.allow_llm_fallback} onChange={(e) => setSettings((p) => ({ ...p, ai_assistant_controls: { ...p.ai_assistant_controls, allow_llm_fallback: e.target.checked } }))} /> Ask before LLM fallback</label>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]">
          <input
            type={showModelApiKey ? "text" : "password"}
            className="rounded border px-3 py-2 text-sm"
            placeholder={
              settings.ai_assistant_controls.model_api_key_masked
                ? `Saved key: ${settings.ai_assistant_controls.model_api_key_masked}`
                : "Enter model API key"
            }
            value={modelApiKeyInput}
            onChange={(e) => setModelApiKeyInput(e.target.value)}
          />
          <button
            type="button"
            className="rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
            onClick={() => setShowModelApiKey((prev) => !prev)}
          >
            {showModelApiKey ? "Hide Key" : "Show Key"}
          </button>
        </div>
        <p className="text-xs text-gray-500">
          {settings.ai_assistant_controls.has_model_api_key
            ? "A model API key is saved. Enter a new key only if you want to replace it."
            : "No model API key saved yet."}
        </p>
      </section>}

      {activeTab === "ai" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold text-gray-800">LLM Usage Cost (EUR / Day)</h3>
          <select
            className="rounded border px-3 py-2 text-sm"
            value={llmDays}
            onChange={(e) => setLlmDays(Number(e.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="rounded border bg-gray-50 px-3 py-2 text-sm">
            <div className="text-gray-500">Total Cost</div>
            <div className="text-xl font-semibold text-emerald-700">
              {new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(llmUsage.total_cost_eur || 0)}
            </div>
          </div>
          <div className="rounded border bg-gray-50 px-3 py-2 text-sm">
            <div className="text-gray-500">Total Calls</div>
            <div className="text-xl font-semibold text-gray-800">{llmUsage.total_calls || 0}</div>
          </div>
          <div className="rounded border bg-gray-50 px-3 py-2 text-sm">
            <div className="text-gray-500">Avg Cost / Day</div>
            <div className="text-xl font-semibold text-indigo-700">
              {new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(
                (llmUsage.total_cost_eur || 0) / Math.max(1, llmUsage.days || llmDays)
              )}
            </div>
          </div>
        </div>

        {llmUsageError && (
          <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {llmUsageError}
          </div>
        )}

        {llmUsageLoading ? (
          <div className="text-sm text-gray-500">Loading LLM usage cost…</div>
        ) : (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={llmUsage.series || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickFormatter={(value) => String(value).slice(5)} />
                <YAxis tickFormatter={(value) => `€${Number(value).toFixed(2)}`} />
                <Tooltip
                  formatter={(value: number) => [`€${Number(value).toFixed(4)}`, "Cost"]}
                  labelFormatter={(label) => `Date: ${label}`}
                />
                <Bar dataKey="cost_eur" fill="#16a34a" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>}

      {activeTab === "dashboard" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Dashboard Preferences</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input type="number" min="1" className="rounded border px-3 py-2 text-sm" value={settings.dashboard_preferences.default_date_range_days} onChange={(e) => setSettings((p) => ({ ...p, dashboard_preferences: { ...p.dashboard_preferences, default_date_range_days: Number(e.target.value) } }))} />
          <select className="rounded border px-3 py-2 text-sm" value={settings.dashboard_preferences.default_grouping} onChange={(e) => setSettings((p) => ({ ...p, dashboard_preferences: { ...p.dashboard_preferences, default_grouping: e.target.value } }))}>
            <option value="developer">developer</option>
            <option value="project">project</option>
            <option value="severity">severity</option>
            <option value="rule_pack">rule_pack</option>
          </select>
          <input type="number" min="0" className="rounded border px-3 py-2 text-sm" value={settings.dashboard_preferences.auto_refresh_interval_sec} onChange={(e) => setSettings((p) => ({ ...p, dashboard_preferences: { ...p.dashboard_preferences, auto_refresh_interval_sec: Number(e.target.value) } }))} />
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
          <label className="flex items-center gap-2"><input type="checkbox" checked={settings.dashboard_preferences.kpi_cards.open_violations} onChange={(e) => setSettings((p) => ({ ...p, dashboard_preferences: { ...p.dashboard_preferences, kpi_cards: { ...p.dashboard_preferences.kpi_cards, open_violations: e.target.checked } } }))} /> Open violations</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={settings.dashboard_preferences.kpi_cards.fixed_rate} onChange={(e) => setSettings((p) => ({ ...p, dashboard_preferences: { ...p.dashboard_preferences, kpi_cards: { ...p.dashboard_preferences.kpi_cards, fixed_rate: e.target.checked } } }))} /> Fixed rate</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={settings.dashboard_preferences.kpi_cards.top_rule_packs} onChange={(e) => setSettings((p) => ({ ...p, dashboard_preferences: { ...p.dashboard_preferences, kpi_cards: { ...p.dashboard_preferences.kpi_cards, top_rule_packs: e.target.checked } } }))} /> Top rule packs</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={settings.dashboard_preferences.kpi_cards.active_developers} onChange={(e) => setSettings((p) => ({ ...p, dashboard_preferences: { ...p.dashboard_preferences, kpi_cards: { ...p.dashboard_preferences.kpi_cards, active_developers: e.target.checked } } }))} /> Active developers</label>
        </div>
        <div className="rounded border border-sky-200 bg-sky-50 p-3">
          <p className="mb-2 text-sm font-medium text-sky-900">Clear Fixed Violations</p>
          <div className="flex justify-start">
            <button
              type="button"
              onClick={clearFixedViolations}
              disabled={clearingViolations}
              className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-60"
            >
              {clearingViolations ? "Clearing..." : "Clear All Fixed Violations"}
            </button>
          </div>
        </div>
      </section>}

      {activeTab === "ops" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Notifications</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <input className="rounded border px-3 py-2 text-sm" placeholder="Channels (comma-separated)" value={arrayToCsv(settings.notifications.channels)} onChange={(e) => setSettings((p) => ({ ...p, notifications: { ...p.notifications, channels: csvToArray(e.target.value) } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Triggers (comma-separated)" value={arrayToCsv(settings.notifications.triggers)} onChange={(e) => setSettings((p) => ({ ...p, notifications: { ...p.notifications, triggers: csvToArray(e.target.value) } }))} />
          <select className="rounded border px-3 py-2 text-sm" value={settings.notifications.digest_frequency} onChange={(e) => setSettings((p) => ({ ...p, notifications: { ...p.notifications, digest_frequency: e.target.value } }))}>
            <option value="instant">instant</option>
            <option value="daily">daily</option>
            <option value="weekly">weekly</option>
          </select>
        </div>
      </section>}

      {activeTab === "ops" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Security & Compliance</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input type="number" min="1" className="rounded border px-3 py-2 text-sm" value={settings.security_compliance.retention_days} onChange={(e) => setSettings((p) => ({ ...p, security_compliance: { ...p.security_compliance, retention_days: Number(e.target.value) } }))} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.security_compliance.pii_masking} onChange={(e) => setSettings((p) => ({ ...p, security_compliance: { ...p.security_compliance, pii_masking: e.target.checked } }))} /> PII masking</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.security_compliance.audit_log_export} onChange={(e) => setSettings((p) => ({ ...p, security_compliance: { ...p.security_compliance, audit_log_export: e.target.checked } }))} /> Audit log export</label>
        </div>
        <input className="w-full rounded border px-3 py-2 text-sm" placeholder="Roles allowed to change settings (comma-separated)" value={arrayToCsv(settings.security_compliance.settings_change_roles)} onChange={(e) => setSettings((p) => ({ ...p, security_compliance: { ...p.security_compliance, settings_change_roles: csvToArray(e.target.value) } }))} />
      </section>}

      {activeTab === "ops" && <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Integrations</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <input className="rounded border px-3 py-2 text-sm" placeholder="SAP endpoint" value={settings.integrations.sap_endpoint} onChange={(e) => setSettings((p) => ({ ...p, integrations: { ...p.integrations, sap_endpoint: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Ticketing provider" value={settings.integrations.ticketing_provider} onChange={(e) => setSettings((p) => ({ ...p, integrations: { ...p.integrations, ticketing_provider: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="CI hook URL" value={settings.integrations.ci_hook_url} onChange={(e) => setSettings((p) => ({ ...p, integrations: { ...p.integrations, ci_hook_url: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Webhook secret" value={settings.integrations.webhook_secret} onChange={(e) => setSettings((p) => ({ ...p, integrations: { ...p.integrations, webhook_secret: e.target.value } }))} />
        </div>
      </section>}
    </div>
  );
}
