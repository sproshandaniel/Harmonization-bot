import { useEffect, useState } from "react";

type AppSettings = {
  workspace_identity: {
    default_project: string;
    timezone: string;
    date_format: string;
    display_name: string;
    email: string;
    role: string;
    team_owner_map: Record<string, string>;
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

export default function Settings() {
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clearingViolations, setClearingViolations] = useState(false);
  const [modelApiKeyInput, setModelApiKeyInput] = useState("");
  const [showModelApiKey, setShowModelApiKey] = useState(false);
  const [clearStartDate, setClearStartDate] = useState("");
  const [clearEndDate, setClearEndDate] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  async function clearViolationsInRange() {
    try {
      setError(null);
      setMessage(null);
      if (!clearStartDate || !clearEndDate) {
        setError("Select both start and end dates.");
        return;
      }
      setClearingViolations(true);
      const query = new URLSearchParams({
        start_date: clearStartDate,
        end_date: clearEndDate,
      }).toString();
      const res = await fetch(`/api/dashboard/violations?${query}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as { deleted: number };
      setMessage(`Deleted ${data.deleted} violation(s).`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to clear violations");
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

      <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Workspace & Identity</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input className="rounded border px-3 py-2 text-sm" placeholder="Default project" value={settings.workspace_identity.default_project} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, default_project: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Timezone" value={settings.workspace_identity.timezone} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, timezone: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Date format" value={settings.workspace_identity.date_format} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, date_format: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Display name" value={settings.workspace_identity.display_name} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, display_name: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Email" value={settings.workspace_identity.email} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, email: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Role" value={settings.workspace_identity.role} onChange={(e) => setSettings((p) => ({ ...p, workspace_identity: { ...p.workspace_identity, role: e.target.value } }))} />
        </div>
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
      </section>

      <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
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
      </section>

      <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
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
      </section>

      <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
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
      </section>

      <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
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
          <p className="mb-2 text-sm font-medium text-sky-900">Clear Previous Violations by Date Range</p>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_1fr_auto]">
            <input
              type="date"
              className="rounded border px-3 py-2 text-sm"
              value={clearStartDate}
              onChange={(e) => setClearStartDate(e.target.value)}
            />
            <input
              type="date"
              className="rounded border px-3 py-2 text-sm"
              value={clearEndDate}
              onChange={(e) => setClearEndDate(e.target.value)}
            />
            <button
              type="button"
              onClick={clearViolationsInRange}
              disabled={clearingViolations}
              className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-60"
            >
              {clearingViolations ? "Clearing..." : "Clear Violations"}
            </button>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
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
      </section>

      <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Security & Compliance</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input type="number" min="1" className="rounded border px-3 py-2 text-sm" value={settings.security_compliance.retention_days} onChange={(e) => setSettings((p) => ({ ...p, security_compliance: { ...p.security_compliance, retention_days: Number(e.target.value) } }))} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.security_compliance.pii_masking} onChange={(e) => setSettings((p) => ({ ...p, security_compliance: { ...p.security_compliance, pii_masking: e.target.checked } }))} /> PII masking</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.security_compliance.audit_log_export} onChange={(e) => setSettings((p) => ({ ...p, security_compliance: { ...p.security_compliance, audit_log_export: e.target.checked } }))} /> Audit log export</label>
        </div>
        <input className="w-full rounded border px-3 py-2 text-sm" placeholder="Roles allowed to change settings (comma-separated)" value={arrayToCsv(settings.security_compliance.settings_change_roles)} onChange={(e) => setSettings((p) => ({ ...p, security_compliance: { ...p.security_compliance, settings_change_roles: csvToArray(e.target.value) } }))} />
      </section>

      <section className="space-y-3 rounded-lg border bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-800">Integrations</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <input className="rounded border px-3 py-2 text-sm" placeholder="SAP endpoint" value={settings.integrations.sap_endpoint} onChange={(e) => setSettings((p) => ({ ...p, integrations: { ...p.integrations, sap_endpoint: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Ticketing provider" value={settings.integrations.ticketing_provider} onChange={(e) => setSettings((p) => ({ ...p, integrations: { ...p.integrations, ticketing_provider: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="CI hook URL" value={settings.integrations.ci_hook_url} onChange={(e) => setSettings((p) => ({ ...p, integrations: { ...p.integrations, ci_hook_url: e.target.value } }))} />
          <input className="rounded border px-3 py-2 text-sm" placeholder="Webhook secret" value={settings.integrations.webhook_secret} onChange={(e) => setSettings((p) => ({ ...p, integrations: { ...p.integrations, webhook_secret: e.target.value } }))} />
        </div>
      </section>
    </div>
  );
}
