import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export default function Dashboard() {
  // Mock KPI data
  const kpis = [
    { title: "Total Rules", value: 120, color: "text-indigo-700" },
    { title: "Violations Today", value: 18, color: "text-red-600" },
    { title: "Compliance Score", value: "93%", color: "text-green-600" },
  ];

  // Mock violation trend data (for chart)
  const trendData = [
    { date: "Mon", violations: 12 },
    { date: "Tue", violations: 10 },
    { date: "Wed", violations: 16 },
    { date: "Thu", violations: 9 },
    { date: "Fri", violations: 18 },
  ];

  // Mock table data
  const violations = [
    {
      rulePack: "abap-core-safety",
      object: "ZHR_PAYROLL.abap",
      transport: "TRK12345",
      developer: "S. Patel",
      severity: "Error",
    },
    {
      rulePack: "abap-naming-conv",
      object: "ZFI_GL_REPORT.abap",
      transport: "TRK67890",
      developer: "R. Kumar",
      severity: "Warning",
    },
    {
      rulePack: "security-base",
      object: "ZMM_PURCHASE_ORDER.abap",
      transport: "TRK54321",
      developer: "M. Lee",
      severity: "Error",
    },
  ];

  return (
    <div className="p-8">
      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-10">
        {kpis.map((kpi) => (
          <div
            key={kpi.title}
            className="bg-white p-6 rounded-lg shadow-sm border border-gray-100"
          >
            <h2 className="text-sm font-medium text-gray-500">
              {kpi.title}
            </h2>
            <p className={`text-3xl font-bold mt-2 ${kpi.color}`}>
              {kpi.value}
            </p>
          </div>
        ))}
      </div>

      {/* Violations Trend */}
      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-100 mb-10">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">
          Violations Trend (This Week)
        </h2>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={trendData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="violations" fill="#6366F1" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Violations Table */}
      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-100">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">
          Violations Summary
        </h2>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse">
            <thead>
              <tr className="border-b text-gray-600 bg-gray-50">
                <th className="py-2 px-3">Rule Pack</th>
                <th className="py-2 px-3">Violation Object</th>
                <th className="py-2 px-3">Transport</th>
                <th className="py-2 px-3">Developer Name</th>
                <th className="py-2 px-3">Severity</th>
              </tr>
            </thead>
            <tbody>
              {violations.map((v, index) => (
                <tr
                  key={index}
                  className="border-b hover:bg-gray-50 transition"
                >
                  <td className="py-2 px-3 font-medium text-gray-800">
                    {v.rulePack}
                  </td>
                  <td className="py-2 px-3 text-gray-700">{v.object}</td>
                  <td className="py-2 px-3 text-gray-600">{v.transport}</td>
                  <td className="py-2 px-3 text-gray-700">{v.developer}</td>
                  <td
                    className={`py-2 px-3 font-semibold ${
                      v.severity === "Error"
                        ? "text-red-600"
                        : "text-yellow-600"
                    }`}
                  >
                    {v.severity}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}