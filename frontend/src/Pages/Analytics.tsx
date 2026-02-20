import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
} from "recharts";

type Summary = {
  total_rules: number;
  saved_rules: number;
  overall_compliance: number;
};

type CompliancePoint = {
  date: string;
  label: string;
  score: number;
  evaluated: number;
  approved: number;
};

type HeatPoint = {
  category: string;
  severity: string;
  count: number;
};

type FunnelPoint = {
  stage: string;
  count: number;
};

type TopViolation = {
  rule_id: string;
  count: number;
  projects: string[];
};

type AnalyticsResponse = {
  summary: Summary;
  compliance_trend: CompliancePoint[];
  violation_heatmap: HeatPoint[];
  lifecycle_funnel: FunnelPoint[];
  top_violations: TopViolation[];
};

type DeveloperSummary = {
  total_violations: number;
  active_developers: number;
  improving_developers: number;
};

type DeveloperTotals = {
  developer: string;
  total: number;
  error: number;
  warning: number;
  info: number;
  other: number;
};

type DeveloperImprovement = {
  developer: string;
  previous_7d: number;
  current_7d: number;
  delta: number;
  improvement_pct: number;
  trend: "improving" | "declining" | "stable";
};

type DeveloperDailyPoint = {
  date: string;
  [developer: string]: string | number;
};

type DeveloperAnalyticsResponse = {
  summary: DeveloperSummary;
  by_developer: DeveloperTotals[];
  improvement: DeveloperImprovement[];
  daily_by_developer: DeveloperDailyPoint[];
};

type AnalyticsEntity = "rules" | "violations" | "developer";
type AnalyticsPeriod = "week" | "month" | "year" | "custom";

const CHART_COLORS = {
  linePrimary: "#2f6fed",
  barCritical: "#c2413b",
  barPositive: "#158f76",
  barNeutral: "#3f5f85",
  grid: "#d7e1ec",
};

const emptyData: AnalyticsResponse = {
  summary: { total_rules: 0, saved_rules: 0, overall_compliance: 0 },
  compliance_trend: [],
  violation_heatmap: [],
  lifecycle_funnel: [],
  top_violations: [],
};

const emptyDeveloperData: DeveloperAnalyticsResponse = {
  summary: { total_violations: 0, active_developers: 0, improving_developers: 0 },
  by_developer: [],
  improvement: [],
  daily_by_developer: [],
};

export default function Analytics() {
  const [data, setData] = useState<AnalyticsResponse>(emptyData);
  const [developerData, setDeveloperData] = useState<DeveloperAnalyticsResponse>(emptyDeveloperData);
  const [developerOptions, setDeveloperOptions] = useState<string[]>([]);
  const [entity, setEntity] = useState<AnalyticsEntity>("rules");
  const [period, setPeriod] = useState<AnalyticsPeriod>("week");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedDeveloper, setSelectedDeveloper] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams();
    params.set("period", period);
    if (period === "custom") {
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);
    }
    const developerParams = new URLSearchParams(params);
    if (entity === "developer" && selectedDeveloper) {
      developerParams.set("developer", selectedDeveloper);
    }
    const run = async () => {
      try {
        setLoading(true);
        setError(null);
        const [overviewRes, developerRes, developerOptionsRes] = await Promise.all([
          fetch(`/api/analytics/overview?${params.toString()}`),
          fetch(`/api/analytics/developers?${developerParams.toString()}`),
          fetch(`/api/analytics/developer-options?${params.toString()}`),
        ]);
        if (!overviewRes.ok) throw new Error(`Analytics API failed (${overviewRes.status})`);
        if (!developerRes.ok) throw new Error(`Developer Analytics API failed (${developerRes.status})`);
        if (!developerOptionsRes.ok) {
          throw new Error(`Developer options API failed (${developerOptionsRes.status})`);
        }
        const overviewJson = (await overviewRes.json()) as AnalyticsResponse;
        const developerJson = (await developerRes.json()) as DeveloperAnalyticsResponse;
        const optionsJson = (await developerOptionsRes.json()) as { developers?: string[] };
        if (active) {
          setData(overviewJson);
          setDeveloperData(developerJson);
          const options = Array.isArray(optionsJson.developers) ? optionsJson.developers : [];
          setDeveloperOptions(options);
          if (entity === "developer" && selectedDeveloper && !options.includes(selectedDeveloper)) {
            setSelectedDeveloper("");
          }
        }
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : "Failed to load analytics";
        if (active) setError(message);
      } finally {
        if (active) setLoading(false);
      }
    };
    void run();
    return () => {
      active = false;
    };
  }, [entity, period, startDate, endDate, selectedDeveloper]);

  const heatData = useMemo(
    () =>
      data.violation_heatmap.map((item) => ({
        name: `${item.category}:${item.severity}`,
        count: item.count,
      })),
    [data.violation_heatmap]
  );

  const totalEvaluated = useMemo(
    () => data.compliance_trend.reduce((acc, item) => acc + item.evaluated, 0),
    [data.compliance_trend]
  );

  const topDeveloperNames = useMemo(
    () => developerData.by_developer.slice(0, 3).map((item) => item.developer),
    [developerData.by_developer]
  );

  const developerTrendColors = ["#2f6fed", "#158f76", "#b45309"];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-indigo-700">Analytics</h2>
        <p className="text-sm text-gray-600 mt-1">
          Compliance, violations and developer insights with time-based filtering.
        </p>
      </div>

      <div className="bg-white border rounded-lg p-4 shadow-sm">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Entity</label>
            <select
              value={entity}
              onChange={(e) => setEntity(e.target.value as AnalyticsEntity)}
              className="w-full border rounded px-2 py-2 text-sm"
            >
              <option value="rules">Rules</option>
              <option value="violations">Violations</option>
              <option value="developer">Developer</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Period</label>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value as AnalyticsPeriod)}
              className="w-full border rounded px-2 py-2 text-sm"
            >
              <option value="week">Last 7 days</option>
              <option value="month">Last 30 days</option>
              <option value="year">Last 365 days</option>
              <option value="custom">Custom range</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">From</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              disabled={period !== "custom"}
              className="w-full border rounded px-2 py-2 text-sm disabled:bg-gray-100"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">To</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              disabled={period !== "custom"}
              className="w-full border rounded px-2 py-2 text-sm disabled:bg-gray-100"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Developer</label>
            <select
              value={selectedDeveloper}
              onChange={(e) => setSelectedDeveloper(e.target.value)}
              disabled={entity !== "developer"}
              className="w-full border rounded px-2 py-2 text-sm disabled:bg-gray-100"
            >
              <option value="">All Developers</option>
              {developerOptions.map((developer) => (
                <option key={developer} value={developer}>
                  {developer}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {entity === "rules" && (
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section className="bg-white border rounded-lg p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Compliance Score Trend (7 days)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.compliance_trend}>
                <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke={CHART_COLORS.linePrimary}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Evaluated this week: {totalEvaluated}
          </p>
        </section>

        <section className="bg-white border rounded-lg p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Violation Heatmap (Category + Severity)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={heatData} barCategoryGap="32%">
                <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" interval={0} angle={-20} height={60} textAnchor="end" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill={CHART_COLORS.barCritical} radius={[3, 3, 0, 0]} barSize={12} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="bg-white border rounded-lg p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Rule Lifecycle Funnel
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.lifecycle_funnel} barCategoryGap="32%">
                <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="stage" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill={CHART_COLORS.barPositive} radius={[3, 3, 0, 0]} barSize={12} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="bg-white border rounded-lg p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Top Repeated Violations
          </h3>
          <div className="overflow-auto max-h-64">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left border-b bg-gray-50">
                  <th className="py-2 px-2">Rule ID</th>
                  <th className="py-2 px-2">Count</th>
                  <th className="py-2 px-2">Projects</th>
                </tr>
              </thead>
              <tbody>
                {data.top_violations.map((item) => (
                  <tr key={item.rule_id} className="border-b">
                    <td className="py-2 px-2 font-medium text-gray-700">
                      {item.rule_id}
                    </td>
                    <td className="py-2 px-2">{item.count}</td>
                    <td className="py-2 px-2 text-xs text-gray-600">
                      {item.projects.join(", ")}
                    </td>
                  </tr>
                ))}
                {!loading && data.top_violations.length === 0 && (
                  <tr>
                    <td className="py-3 px-2 text-gray-500" colSpan={3}>
                      No rule events yet. Extract and save rules to populate analytics.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      )}

      {entity !== "rules" && (
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <p className="text-xs text-gray-500">Total Violations</p>
          <p className="text-2xl font-semibold text-red-600">
            {developerData.summary.total_violations}
          </p>
        </div>
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <p className="text-xs text-gray-500">Active Developers</p>
          <p className="text-2xl font-semibold text-indigo-700">
            {developerData.summary.active_developers}
          </p>
        </div>
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <p className="text-xs text-gray-500">Developers Improving (7d)</p>
          <p className="text-2xl font-semibold text-green-600">
            {developerData.summary.improving_developers}
          </p>
        </div>
      </div>
      )}

      {entity !== "rules" && (
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section className="bg-white border rounded-lg p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Violations Per Developer
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={developerData.by_developer} barCategoryGap="30%">
                <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="developer" interval={0} angle={-20} height={70} textAnchor="end" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="total" fill={CHART_COLORS.barNeutral} radius={[3, 3, 0, 0]} barSize={12} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="bg-white border rounded-lg p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Daily Trend (Top 3 Developers)
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={developerData.daily_by_developer}>
                <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                {topDeveloperNames.map((name, idx) => (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={developerTrendColors[idx % developerTrendColors.length]}
                    strokeWidth={2}
                    dot={{ r: 2 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="bg-white border rounded-lg p-4 shadow-sm xl:col-span-2">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Developer Performance Improvement (Current 7d vs Previous 7d)
          </h3>
          <div className="overflow-auto max-h-72">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left border-b bg-gray-50">
                  <th className="py-2 px-2">Developer</th>
                  <th className="py-2 px-2">Prev 7d</th>
                  <th className="py-2 px-2">Current 7d</th>
                  <th className="py-2 px-2">Delta</th>
                  <th className="py-2 px-2">Improvement</th>
                  <th className="py-2 px-2">Trend</th>
                </tr>
              </thead>
              <tbody>
                {developerData.improvement.map((item) => (
                  <tr key={item.developer} className="border-b">
                    <td className="py-2 px-2 font-medium text-gray-700">{item.developer}</td>
                    <td className="py-2 px-2">{item.previous_7d}</td>
                    <td className="py-2 px-2">{item.current_7d}</td>
                    <td className={`py-2 px-2 ${item.delta > 0 ? "text-red-600" : item.delta < 0 ? "text-green-600" : "text-gray-700"}`}>
                      {item.delta}
                    </td>
                    <td className="py-2 px-2">{item.improvement_pct}%</td>
                    <td className="py-2 px-2 capitalize">{item.trend}</td>
                  </tr>
                ))}
                {!loading && developerData.improvement.length === 0 && (
                  <tr>
                    <td className="py-3 px-2 text-gray-500" colSpan={6}>
                      No developer violation data yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      )}
    </div>
  );
}
