import { useEffect, useState } from "react";
import { FolderPlus, Wand2, FileText, Code, Layout, Tag, Zap, Puzzle } from "lucide-react";
import RuleExtractor from "./RuleExtractor";

export default function RulePacks() {
  const [activeTab, setActiveTab] = useState<"packs" | "extractor">("packs");
  const [kpis, setKpis] = useState({
    code: 0,
    design: 0,
    naming: 0,
    performance: 0,
    template: 0,
    total: 0,
  });

  // 🧮 Fetch KPI summary (mock or from backend)
  async function fetchKpis() {
    try {
      const res = await fetch("/api/rules/summary");
      if (res.ok) {
        const data = await res.json();
        setKpis(data);
      } else {
        // fallback mock
        setKpis({
          code: 58,
          design: 23,
          naming: 35,
          performance: 19,
          template: 12,
          total: 147,
        });
      }
    } catch (err) {
      console.error(err);
    }
  }

  useEffect(() => {
    fetchKpis();
  }, []);

  return (
    <div className="p-6 space-y-6">
      {/* ---------- KPI CARDS ---------- */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <KpiCard icon={<Code size={20} />} label="Code Rules" value={kpis.code} color="text-indigo-600" />
        <KpiCard icon={<Layout size={20} />} label="Design Rules" value={kpis.design} color="text-blue-600" />
        <KpiCard icon={<Tag size={20} />} label="Naming Conventions" value={kpis.naming} color="text-emerald-600" />
        <KpiCard icon={<Zap size={20} />} label="Performance Rules" value={kpis.performance} color="text-orange-600" />
        <KpiCard icon={<Puzzle size={20} />} label="Templates" value={kpis.template} color="text-violet-600" />
      </div>

      {/* ---------- HEADER ---------- */}
      <div className="flex items-center justify-between pt-4">
        <h1 className="text-2xl font-semibold text-indigo-700 flex items-center gap-2">
          <FileText size={20} /> Rule Packs
        </h1>

        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab("packs")}
            className={`px-4 py-2 rounded ${
              activeTab === "packs"
                ? "bg-indigo-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            View Packs
          </button>
          <button
            onClick={() => setActiveTab("extractor")}
            className={`px-4 py-2 rounded flex items-center gap-1 ${
              activeTab === "extractor"
                ? "bg-indigo-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            <Wand2 size={16} /> Rule Extractor
          </button>
        </div>
      </div>

      {/* ---------- TAB CONTENT ---------- */}
      {activeTab === "packs" ? <PacksList /> : <RuleExtractorWrapper />}
    </div>
  );
}

/* ---------- KPI CARD COMPONENT ---------- */
function KpiCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  color: string;
}) {
  return (
    <div className="bg-white rounded-lg shadow-sm border p-4 flex flex-col">
      <div className="flex items-center justify-between">
        <div className={`text-xl font-bold ${color}`}>{value}</div>
        <div className={`opacity-70 ${color}`}>{icon}</div>
      </div>
      <div className="text-sm text-gray-600 mt-2">{label}</div>
    </div>
  );
}

/* ---------- PACKS LIST PLACEHOLDER ---------- */
function PacksList() {
  return (
    <div className="bg-white p-6 rounded-lg shadow border">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <FolderPlus size={18} /> Existing Rule Packs
      </h2>
      <p className="text-gray-600 text-sm">
        This section lists all rule packs with versions and rule counts.
      </p>
      {/* replace with your existing packs table or cards */}
    </div>
  );
}

/* ---------- WRAPPER FOR RULE EXTRACTOR ---------- */
function RuleExtractorWrapper() {
  return (
    <div className="bg-white rounded-lg shadow border">
      <RuleExtractor />
    </div>
  );
}
