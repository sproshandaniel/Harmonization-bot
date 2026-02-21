import { useCallback, useEffect, useRef, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

type DashboardKpi = {
  title: string;
  value: number | string;
  color: string;
};

type DashboardTrend = {
  date: string;
  violations: number;
};

type DashboardViolation = {
  rulePack: string;
  object: string;
  transport: string;
  developer: string;
  severity: string;
  status?: string;
  date?: string;
};

type DashboardData = {
  kpis: DashboardKpi[];
  trendData: DashboardTrend[];
  violations: DashboardViolation[];
};

const CHART_COLORS = {
  barPrimary: "#0f4da1",
  grid: "#cfe0f2",
  tooltipBg: "#f8fbff",
  tooltipBorder: "#b8d0ea",
};

const initialData: DashboardData = {
  kpis: [],
  trendData: [],
  violations: [],
};

export default function Dashboard() {
  const [data, setData] = useState<DashboardData>(initialData);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const loadDashboard = useCallback(async () => {
    try {
      setError(null);
      const res = await fetch("/api/dashboard/overview");
      if (!res.ok) throw new Error(`Dashboard API failed (${res.status})`);
      const json = (await res.json()) as DashboardData;
      if (!mountedRef.current) return;
      setData(json);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load dashboard";
      if (mountedRef.current) setError(message);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void loadDashboard();
    const onManualRefresh = () => {
      void loadDashboard();
    };
    window.addEventListener("hb-dashboard-refresh", onManualRefresh);
    const intervalId = window.setInterval(() => {
      void loadDashboard();
    }, 30000);
    return () => {
      mountedRef.current = false;
      window.clearInterval(intervalId);
      window.removeEventListener("hb-dashboard-refresh", onManualRefresh);
    };
  }, [loadDashboard]);

  return (
    <div className="min-h-full bg-gray-100 p-8">
      {error && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
        {data.kpis.map((kpi) => (
          <div
            key={kpi.title}
            className="bg-gradient-to-b from-white to-gray-50 p-6 rounded-lg shadow-sm border border-gray-200"
          >
            <h2 className="text-sm font-medium text-gray-600">
              {kpi.title}
            </h2>
            <p className={`text-3xl font-bold mt-2 text-gray-800 ${kpi.color}`}>
              {kpi.value}
            </p>
          </div>
        ))}
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 mb-10">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Violations Trend (This Week)
        </h2>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={data.trendData} barCategoryGap="28%">
            <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" stroke="#4a6484" />
            <YAxis stroke="#4a6484" />
            <Tooltip contentStyle={{ backgroundColor: CHART_COLORS.tooltipBg, borderColor: CHART_COLORS.tooltipBorder }} />
            <Bar dataKey="violations" fill={CHART_COLORS.barPrimary} radius={[3, 3, 0, 0]} barSize={14} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Violations Summary
        </h2>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-gray-700 bg-gray-50">
                <th className="py-2 px-3">Rule Pack</th>
                <th className="py-2 px-3">Violation Object</th>
                <th className="py-2 px-3">Transport</th>
                <th className="py-2 px-3">Developer Name</th>
                <th className="py-2 px-3">Date</th>
                <th className="py-2 px-3">Severity</th>
                <th className="py-2 px-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.violations.map((v, index) => {
                  const statusText = (v.status || "Not Fixed").trim();
                  const normalizedStatus = statusText.toLowerCase().replace(/\s+/g, " ");
                  const statusClass =
                    normalizedStatus === "fixed"
                      ? "text-emerald-700 font-semibold"
                      : normalizedStatus === "not fixed"
                      ? "text-red-700 font-semibold"
                      : "text-gray-700";
                  return (
                <tr
                  key={`${v.transport}-${index}`}
                  className="border-b border-gray-100 hover:bg-gray-50 transition"
                >
                  <td className="py-2 px-3 font-medium text-gray-800">
                    {v.rulePack}
                  </td>
                  <td className="py-2 px-3 text-gray-700">{v.object}</td>
                  <td className="py-2 px-3 text-gray-600">{(v.transport || "").trim() || "-"}</td>
                  <td className="py-2 px-3 text-gray-700">{v.developer}</td>
                  <td className="py-2 px-3 text-gray-700">{v.date || "-"}</td>
                  <td
                    className={`py-2 px-3 font-semibold ${
                      v.severity === "Error"
                        ? "text-gray-700"
                        : "text-gray-500"
                    }`}
                  >
                    {v.severity}
                  </td>
                  <td className={`py-2 px-3 ${statusClass}`}>{statusText}</td>
                </tr>
                  );
                })}
              {data.violations.length === 0 && (
                <tr>
                  <td className="py-3 px-3 text-gray-500" colSpan={7}>
                    No violations available yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
