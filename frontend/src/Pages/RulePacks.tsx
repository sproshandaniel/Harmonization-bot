import { useEffect, useMemo, useState } from "react";
import {
  Wand2,
  FileText,
  Code,
  Layout,
  Tag,
  Zap,
  Puzzle,
  FolderPlus,
  X,
  Edit3,
} from "lucide-react";
import RuleExtractor from "./RuleExtractor";
import Modal from "../Components/modal";
import yaml from "js-yaml";
import WizardFlowchart from "../Components/WizardFlowchart";

type RulePack = {
  id: string;
  name: string;
  status: string;
  rule_count: number;
  created_at?: string | null;
};

type PackRule = {
  db_id?: number;
  yaml: string;
  confidence: number;
  category?: string;
  created_by?: string;
  _id?: string;
  _severity?: string;
  status?: string;
  rule_pack?: string;
};

type WizardFlowStep = {
  stepNo: number;
  title: string;
  dependsOn: number[];
};

export default function RulePacks() {
  const currentUser = (localStorage.getItem("hb_user_email") || "").trim().toLowerCase();
  const [activeTab, setActiveTab] = useState<"packs" | "extractor">("packs");
  const [kpis, setKpis] = useState({
    code: 0,
    design: 0,
    naming: 0,
    performance: 0,
    code_total: 0,
    code_naming: 0,
    code_performance: 0,
    template: 0,
    wizard: 0,
    total: 0,
  });

  const [packs, setPacks] = useState<RulePack[]>([]);
  const [loadingPacks, setLoadingPacks] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [newPackName, setNewPackName] = useState("");
  const [creatingPack, setCreatingPack] = useState(false);

  const [packModalOpen, setPackModalOpen] = useState(false);
  const [selectedPackName, setSelectedPackName] = useState("");
  const [selectedPackRules, setSelectedPackRules] = useState<PackRule[]>([]);
  const [ruleSearch, setRuleSearch] = useState("");
  const [loadingPackRules, setLoadingPackRules] = useState(false);
  const [expandedRuleKeys, setExpandedRuleKeys] = useState<Set<string>>(new Set());
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [noticeMessage, setNoticeMessage] = useState("");
  const [confirmDeletePackName, setConfirmDeletePackName] = useState<string | null>(null);
  const [confirmDeleteRuleId, setConfirmDeleteRuleId] = useState<number | null>(null);
  const [confirmDeleteWizardId, setConfirmDeleteWizardId] = useState<string | null>(null);
  const [expandedWizardKeys, setExpandedWizardKeys] = useState<Set<string>>(new Set());
  const [editYamlOpen, setEditYamlOpen] = useState(false);
  const [editingRuleDbId, setEditingRuleDbId] = useState<number | null>(null);
  const [editingYaml, setEditingYaml] = useState("");
  const [editingYamlError, setEditingYamlError] = useState<string | null>(null);
  const [savingEditYaml, setSavingEditYaml] = useState(false);

  function showNotice(message: string) {
    setNoticeMessage(message);
    setNoticeOpen(true);
  }

  async function fetchKpis() {
    try {
      const res = await fetch("/api/rules/summary");
      if (!res.ok) throw new Error(`KPI API failed (${res.status})`);
      const data = await res.json();
      setKpis(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load KPI summary.";
      setError(message);
      showNotice(message);
    }
  }

  async function refreshRulePackData() {
    await fetchKpis();
    if (activeTab === "packs") {
      await loadPacks();
    }
  }

  useEffect(() => {
    void fetchKpis();
  }, []);

  useEffect(() => {
    if (activeTab === "packs") {
      void refreshRulePackData();
    }
  }, [activeTab]);

  async function loadPacks() {
    try {
      setLoadingPacks(true);
      setError(null);
      const res = await fetch("/api/packs");
      if (!res.ok) throw new Error(`Packs API failed (${res.status})`);
      const data = await res.json();
      setPacks(Array.isArray(data?.packs) ? data.packs : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load packs");
    } finally {
      setLoadingPacks(false);
    }
  }

  async function createPack() {
    const name = newPackName.trim();
    if (!name) {
      showNotice("Enter a pack name.");
      return;
    }
    try {
      setCreatingPack(true);
      setError(null);
      const res = await fetch("/api/packs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          status: "draft",
          rules: [],
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setNewPackName("");
      await refreshRulePackData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create pack");
    } finally {
      setCreatingPack(false);
    }
  }

  async function openPackDialog(packName: string) {
    try {
      setSelectedPackName(packName);
      setSelectedPackRules([]);
      setRuleSearch("");
      setExpandedRuleKeys(new Set());
      setPackModalOpen(true);
      setLoadingPackRules(true);
      const res = await fetch(`/api/packs/${encodeURIComponent(packName)}/rules`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSelectedPackRules(Array.isArray(data?.rules) ? data.rules : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load rules for pack");
    } finally {
      setLoadingPackRules(false);
    }
  }

  async function performDeletePack(packName: string) {
    try {
      setError(null);
      const res = await fetch(`/api/packs/${encodeURIComponent(packName)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(await res.text());
      if (selectedPackName === packName) {
        setPackModalOpen(false);
        setSelectedPackName("");
        setSelectedPackRules([]);
      }
      await refreshRulePackData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete pack");
    }
  }

  async function performDeleteRuleFromPack(ruleDbId?: number) {
    if (!selectedPackName || !ruleDbId) return;
    try {
      setError(null);
      const res = await fetch(
        `/api/packs/${encodeURIComponent(selectedPackName)}/rules/${ruleDbId}`,
        { method: "DELETE" }
      );
      if (!res.ok) throw new Error(await res.text());
      setSelectedPackRules((prev) => prev.filter((r) => r.db_id !== ruleDbId));
      await refreshRulePackData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete rule");
    }
  }

  async function performDeleteWizard(wizardId: string) {
    try {
      setError(null);
      const res = await fetch(`/api/wizards/${encodeURIComponent(wizardId)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(await res.text());
      setSelectedPackRules((prev) =>
        prev.filter((rule) => {
          if ((rule.category || "").toLowerCase() !== "wizard") return true;
          try {
            const parsed: any = yaml.load(rule.yaml);
            return String(parsed?.wizard?.wizard_id || "") !== wizardId;
          } catch {
            return true;
          }
        })
      );
      await refreshRulePackData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to delete wizard";
      setError(message);
      showNotice(message);
    }
  }

  function closePackModal() {
    setPackModalOpen(false);
    setExpandedRuleKeys(new Set());
  }

  function openEditYamlDialog(rule: PackRule) {
    if (!rule.db_id) {
      showNotice("Only persisted rules can be edited from this view.");
      return;
    }
    setEditingRuleDbId(rule.db_id);
    setEditingYaml(rule.yaml || "");
    setEditingYamlError(null);
    setEditYamlOpen(true);
  }

  function onEditYamlChange(next: string) {
    setEditingYaml(next);
    try {
      const parsed = yaml.load(next);
      if (!parsed || typeof parsed !== "object") {
        setEditingYamlError("YAML must be an object/mapping.");
        return;
      }
      setEditingYamlError(null);
    } catch (err: any) {
      setEditingYamlError(err?.message || "Invalid YAML.");
    }
  }

  async function saveEditedYaml() {
    if (!selectedPackName || !editingRuleDbId) return;
    const payloadYaml = editingYaml.trim();
    if (!payloadYaml) {
      setEditingYamlError("YAML cannot be empty.");
      return;
    }
    try {
      const parsed = yaml.load(payloadYaml);
      if (!parsed || typeof parsed !== "object") {
        setEditingYamlError("YAML must be an object/mapping.");
        return;
      }
    } catch (err: any) {
      setEditingYamlError(err?.message || "Invalid YAML.");
      return;
    }
    try {
      setSavingEditYaml(true);
      const res = await fetch(
        `/api/packs/${encodeURIComponent(selectedPackName)}/rules/${editingRuleDbId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ yaml: payloadYaml }),
        }
      );
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const updated = data?.rule;
      setSelectedPackRules((prev) =>
        prev.map((rule) =>
          rule.db_id === editingRuleDbId
            ? {
                ...rule,
                yaml: updated?.yaml || payloadYaml,
                confidence: Number(updated?.confidence ?? rule.confidence ?? 0),
                category: updated?.category || rule.category,
                _id: updated?._id || rule._id,
                _severity: updated?._severity || rule._severity,
                status: updated?.status || rule.status,
              }
            : rule
        )
      );
      setEditYamlOpen(false);
      setEditingRuleDbId(null);
      setEditingYaml("");
      setEditingYamlError(null);
      await refreshRulePackData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to update YAML";
      setEditingYamlError(message);
    } finally {
      setSavingEditYaml(false);
    }
  }

  function toggleRuleExpanded(ruleKey: string) {
    setExpandedRuleKeys((prev) => {
      const next = new Set(prev);
      if (next.has(ruleKey)) next.delete(ruleKey);
      else next.add(ruleKey);
      return next;
    });
  }

  function toggleWizardExpanded(wizardKey: string) {
    setExpandedWizardKeys((prev) => {
      const next = new Set(prev);
      if (next.has(wizardKey)) next.delete(wizardKey);
      else next.add(wizardKey);
      return next;
    });
  }

  const wizardGroups = useMemo(() => {
    const query = ruleSearch.trim().toLowerCase();
    const filteredRules = query
      ? selectedPackRules.filter((rule) => {
          const haystack = [
            rule._id || "",
            rule.category || "",
            rule._severity || "",
            rule.rule_pack || "",
            rule.yaml || "",
          ]
            .join("\n")
            .toLowerCase();
          return haystack.includes(query);
        })
      : selectedPackRules;

    const groups: Record<
      string,
      { name: string; steps: PackRule[]; deleteId: string; flowSteps: WizardFlowStep[] }
    > = {};
    for (const rule of filteredRules) {
      if ((rule.category || "").toLowerCase() !== "wizard") continue;
      let wizardId = "";
      let wizardName = "Wizard";
      let flowStep: WizardFlowStep | null = null;
      try {
        const parsed: any = yaml.load(rule.yaml);
        const wizard = parsed?.wizard || {};
        wizardId = String(wizard.wizard_id || "");
        wizardName = String(wizard.wizard_name || wizardName);
        const stepNo = Number(wizard.step_no);
        const dependsRaw = Array.isArray(wizard.depends_on) ? wizard.depends_on : [];
        const dependsOn = dependsRaw
          .map((x: unknown) => Number(x))
          .filter((x: number) => Number.isFinite(x) && x >= 1);
        if (Number.isFinite(stepNo) && stepNo >= 1) {
          flowStep = {
            stepNo,
            title: String(wizard.step_title || parsed?.title || `Step ${stepNo}`).trim(),
            dependsOn,
          };
        }
      } catch {
        // ignore parse errors and fall back to defaults
      }
      const fallbackId = String(rule._id || wizardName || "wizard");
      const groupId = wizardId || fallbackId;
      if (!groups[groupId]) {
        groups[groupId] = {
          name: wizardName,
          steps: [],
          deleteId: wizardId || fallbackId,
          flowSteps: [],
        };
      }
      groups[groupId].steps.push(rule);
      if (flowStep) {
        const existingIdx = groups[groupId].flowSteps.findIndex((s) => s.stepNo === flowStep!.stepNo);
        if (existingIdx >= 0) groups[groupId].flowSteps[existingIdx] = flowStep;
        else groups[groupId].flowSteps.push(flowStep);
      }
    }
    return Object.entries(groups).map(([id, data]) => {
      const sortedSteps = [...data.flowSteps].sort((a, b) => a.stepNo - b.stepNo);
      return {
        id,
        name: data.name,
        steps: data.steps,
        deleteId: data.deleteId,
        flowSteps: sortedSteps,
      };
    });
  }, [selectedPackRules, ruleSearch]);

  const visibleNonWizardRules = useMemo(() => {
    const query = ruleSearch.trim().toLowerCase();
    return selectedPackRules.filter((rule) => {
      if ((rule.category || "").toLowerCase() === "wizard") return false;
      if (!query) return true;
      const haystack = [
        rule._id || "",
        rule.category || "",
        rule._severity || "",
        rule.rule_pack || "",
        rule.yaml || "",
      ]
        .join("\n")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [selectedPackRules, ruleSearch]);

  const mergedCodeTotal = kpis.code_total || (kpis.code + kpis.naming + kpis.performance);
  const mergedNamingTotal = kpis.code_naming || kpis.naming;
  const mergedPerformanceTotal = kpis.code_performance || kpis.performance;

  return (
    <div className="p-6 space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard icon={<Code size={20} />} label="Total Code Rules" value={mergedCodeTotal} color="text-indigo-600" />
        <KpiCard icon={<Tag size={20} />} label="Code: Naming" value={mergedNamingTotal} color="text-emerald-600" />
        <KpiCard icon={<Zap size={20} />} label="Code: Performance" value={mergedPerformanceTotal} color="text-orange-600" />
        <KpiCard icon={<Layout size={20} />} label="Design Rules" value={kpis.design} color="text-blue-600" />
        <KpiCard icon={<Puzzle size={20} />} label="Templates" value={kpis.template} color="text-violet-600" />
        <KpiCard icon={<Wand2 size={20} />} label="Wizards" value={kpis.wizard} color="text-fuchsia-600" />
      </div>

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

      {activeTab === "packs" ? (
        <div className="bg-white p-6 rounded-lg shadow border space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="border rounded px-3 py-2 text-sm min-w-[280px]"
              placeholder="New rule pack name"
              value={newPackName}
              onChange={(e) => setNewPackName(e.target.value)}
            />
            <button
              onClick={createPack}
              disabled={creatingPack}
              className="inline-flex items-center gap-1 px-4 py-2 rounded bg-indigo-600 text-white text-sm hover:bg-indigo-700 disabled:opacity-60"
            >
              <FolderPlus size={16} />
              {creatingPack ? "Creating..." : "Create Pack"}
            </button>
          </div>

          {error && (
            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          {loadingPacks ? (
            <p className="text-sm text-gray-500">Loading packs...</p>
          ) : packs.length === 0 ? (
            <p className="text-sm text-gray-500">No packs available yet.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {packs.map((pack) => (
                <div
                  key={pack.id}
                  className="relative text-left border rounded-lg p-4 hover:bg-gray-50 transition space-y-2"
                >
                  <button
                    onClick={() => setConfirmDeletePackName(pack.name)}
                    className="absolute right-2 top-2 inline-flex items-center justify-center w-7 h-7 rounded bg-red-50 text-red-600 hover:bg-red-100"
                    title="Delete pack"
                    aria-label={`Delete pack ${pack.name}`}
                  >
                    <X size={14} />
                  </button>
                  <button
                    onClick={() => openPackDialog(pack.name)}
                    className="w-full text-left pr-10"
                  >
                    <div className="font-semibold text-gray-800">{pack.name}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {pack.rule_count} rule(s) | {pack.status}
                    </div>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <RuleExtractorWrapper onRuleSaved={refreshRulePackData} />
      )}

      <Modal
        open={packModalOpen}
        onClose={closePackModal}
        title={`Rules in Pack: ${selectedPackName || "-"}`}
        footer={
          <div className="flex justify-end">
            <button
              onClick={closePackModal}
              className="px-3 py-1.5 rounded bg-indigo-600 text-white"
            >
              Close
            </button>
          </div>
        }
      >
        {!loadingPackRules && selectedPackRules.length > 0 && (
          <div className="mb-3">
            <input
              className="w-full border rounded px-3 py-2 text-sm"
              placeholder="Search rules in this pack (id, YAML, severity, category)"
              value={ruleSearch}
              onChange={(e) => setRuleSearch(e.target.value)}
            />
          </div>
        )}
        {loadingPackRules ? (
          <p className="text-sm text-gray-500">Loading rules...</p>
        ) : selectedPackRules.length === 0 ? (
          <p className="text-sm text-gray-500">No rules found in this pack.</p>
        ) : ruleSearch.trim() && wizardGroups.length === 0 && visibleNonWizardRules.length === 0 ? (
          <p className="text-sm text-gray-500">No matching rules found for "{ruleSearch.trim()}".</p>
        ) : wizardGroups.length > 0 ? (
          <div className="space-y-3 max-h-[62vh] overflow-y-auto pr-1">
            {wizardGroups.map((wizard) => {
              const isOpen = expandedWizardKeys.has(wizard.id);
              return (
                <div key={wizard.id} className="border rounded-lg overflow-hidden">
                  <div className="px-3 py-2 bg-gray-50 border-b flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-gray-800 truncate">
                      {wizard.name}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleWizardExpanded(wizard.id)}
                        className="text-xs text-indigo-600 hover:text-indigo-800"
                      >
                        {isOpen ? "Hide steps" : `Show steps (${wizard.steps.length})`}
                      </button>
                      {wizard.deleteId !== "wizard" && (
                        <button
                          onClick={() => setConfirmDeleteWizardId(wizard.deleteId)}
                          className="inline-flex items-center justify-center w-7 h-7 rounded bg-red-50 text-red-600 hover:bg-red-100"
                          title="Delete wizard"
                          aria-label={`Delete wizard ${wizard.name}`}
                        >
                          <X size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                  {isOpen && (
                    <div className="space-y-3 p-3 bg-white">
                      {wizard.flowSteps.length > 0 && (
                        <div className="rounded border border-indigo-200 bg-indigo-50 px-3 py-2 space-y-2">
                          <div className="text-xs font-semibold text-indigo-800">Workflow Chart</div>
                          <div className="text-[11px] text-indigo-700">
                            Solid arrows are sequence; dotted arrows are dependencies.
                          </div>
                          <WizardFlowchart steps={wizard.flowSteps} className="bg-white border-indigo-200" />
                        </div>
                      )}
                      {wizard.steps.map((rule, idx) => (
                        (() => {
                          const canEdit = !!rule.db_id && (!rule.created_by || String(rule.created_by).toLowerCase() === currentUser);
                          return (
                        <div
                          key={`${rule._id || "rule"}-${idx}`}
                          className="border rounded-lg overflow-hidden"
                        >
                          <div className="px-3 py-2 bg-gray-50 border-b flex items-center justify-between">
                            <div className="text-sm font-medium text-gray-800 truncate">
                              {rule._id || `Step ${idx + 1}`}
                            </div>
                            <div className="text-xs text-gray-600">
                              {rule.category || "wizard"} | {rule._severity || "MAJOR"} |{" "}
                              {Math.round((rule.confidence || 0) * 100)}%
                            </div>
                          </div>
                          <div className="px-3 py-2 bg-white border-b">
                            <button
                              onClick={() => toggleRuleExpanded(String(rule._id ?? idx))}
                              className="text-xs text-indigo-600 hover:text-indigo-800"
                            >
                              {expandedRuleKeys.has(String(rule._id ?? idx)) ? "Hide YAML" : "Show YAML"}
                            </button>
                            {canEdit ? (
                              <button
                                onClick={() => openEditYamlDialog(rule)}
                                className="ml-3 text-xs text-indigo-600 hover:text-indigo-800 inline-flex items-center gap-1"
                              >
                                <Edit3 size={12} />
                                Edit YAML
                              </button>
                            ) : null}
                          </div>
                          {expandedRuleKeys.has(String(rule._id ?? idx)) && (
                            <pre className="bg-gray-900 text-gray-100 text-xs p-3 overflow-auto max-h-56">
                              {rule.yaml}
                            </pre>
                          )}
                        </div>
                          );
                        })()
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="space-y-3 max-h-[62vh] overflow-y-auto pr-1">
            {visibleNonWizardRules.map((rule, idx) => {
              const canEdit = !!rule.db_id && (!rule.created_by || String(rule.created_by).toLowerCase() === currentUser);
              return (
              <div key={`${rule._id || "rule"}-${idx}`} className="relative border rounded-lg overflow-hidden">
                <div className="px-3 py-2 bg-gray-50 border-b flex items-center justify-between pr-10 gap-2">
                  <div className="text-sm font-medium text-gray-800 truncate">{rule._id || `Rule ${idx + 1}`}</div>
                  <div className="text-xs text-gray-600">
                    {rule.category || "code"} | {rule._severity || "MAJOR"} | {Math.round((rule.confidence || 0) * 100)}%
                  </div>
                </div>
                {canEdit ? (
                  <button
                    onClick={() => setConfirmDeleteRuleId(rule.db_id || null)}
                    className="absolute right-2 top-2 inline-flex items-center justify-center w-7 h-7 rounded bg-red-50 text-red-600 hover:bg-red-100"
                    title="Delete rule"
                    aria-label={`Delete rule ${rule._id || idx + 1}`}
                  >
                    <X size={14} />
                  </button>
                ) : null}
                <div className="px-3 py-2 bg-white border-b">
                  <button
                    onClick={() => toggleRuleExpanded(String(rule.db_id ?? idx))}
                    className="text-xs text-indigo-600 hover:text-indigo-800"
                  >
                    {expandedRuleKeys.has(String(rule.db_id ?? idx)) ? "Hide YAML" : "Show YAML"}
                  </button>
                  {canEdit ? (
                    <button
                      onClick={() => openEditYamlDialog(rule)}
                      className="ml-3 text-xs text-indigo-600 hover:text-indigo-800 inline-flex items-center gap-1"
                    >
                      <Edit3 size={12} />
                      Edit YAML
                    </button>
                  ) : null}
                </div>
                {expandedRuleKeys.has(String(rule.db_id ?? idx)) && (
                  <pre className="bg-gray-900 text-gray-100 text-xs p-3 overflow-auto max-h-56">
                    {rule.yaml}
                  </pre>
                )}
              </div>
              );
            })}
          </div>
        )}
      </Modal>

      <Modal
        open={noticeOpen}
        onClose={() => setNoticeOpen(false)}
        title="Message"
        footer={
          <div className="flex justify-end">
            <button
              onClick={() => setNoticeOpen(false)}
              className="px-3 py-1.5 rounded bg-indigo-600 text-white"
            >
              OK
            </button>
          </div>
        }
      >
        <div className="text-sm text-gray-700">{noticeMessage}</div>
      </Modal>

      <Modal
        open={editYamlOpen}
        onClose={() => {
          if (savingEditYaml) return;
          setEditYamlOpen(false);
        }}
        title="Edit Saved YAML"
        footer={
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setEditYamlOpen(false)}
              className="px-3 py-1.5 rounded border"
              disabled={savingEditYaml}
            >
              Cancel
            </button>
            <button
              onClick={saveEditedYaml}
              className="px-3 py-1.5 rounded bg-indigo-600 text-white disabled:opacity-60"
              disabled={savingEditYaml || !!editingYamlError}
            >
              {savingEditYaml ? "Saving..." : "Save YAML"}
            </button>
          </div>
        }
      >
        <div className="space-y-2">
          <textarea
            value={editingYaml}
            onChange={(e) => onEditYamlChange(e.target.value)}
            className="w-full min-h-[280px] rounded border px-3 py-2 text-xs font-mono"
          />
          {editingYamlError ? (
            <div className="text-xs text-red-700">{editingYamlError}</div>
          ) : (
            <div className="text-xs text-emerald-700">Valid YAML</div>
          )}
        </div>
      </Modal>

      <Modal
        open={!!confirmDeletePackName}
        onClose={() => setConfirmDeletePackName(null)}
        title="Confirm Delete Pack"
        footer={
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setConfirmDeletePackName(null)}
              className="px-3 py-1.5 rounded border"
            >
              Cancel
            </button>
            <button
              onClick={async () => {
                if (!confirmDeletePackName) return;
                const packName = confirmDeletePackName;
                setConfirmDeletePackName(null);
                await performDeletePack(packName);
              }}
              className="px-3 py-1.5 rounded bg-red-600 text-white"
            >
              Delete
            </button>
          </div>
        }
      >
        <div className="text-sm text-gray-700">
          {confirmDeletePackName
            ? `Delete rule pack "${confirmDeletePackName}" and all associated rules?`
            : ""}
        </div>
      </Modal>

      <Modal
        open={confirmDeleteRuleId !== null}
        onClose={() => setConfirmDeleteRuleId(null)}
        title="Confirm Delete Rule"
        footer={
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setConfirmDeleteRuleId(null)}
              className="px-3 py-1.5 rounded border"
            >
              Cancel
            </button>
            <button
              onClick={async () => {
                const ruleId = confirmDeleteRuleId;
                setConfirmDeleteRuleId(null);
                await performDeleteRuleFromPack(ruleId ?? undefined);
              }}
              className="px-3 py-1.5 rounded bg-red-600 text-white"
            >
              Delete
            </button>
          </div>
        }
      >
        <div className="text-sm text-gray-700">
          Delete this rule from the selected pack?
        </div>
      </Modal>

      <Modal
        open={!!confirmDeleteWizardId}
        onClose={() => setConfirmDeleteWizardId(null)}
        title="Confirm Delete Wizard"
        footer={
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setConfirmDeleteWizardId(null)}
              className="px-3 py-1.5 rounded border"
            >
              Cancel
            </button>
            <button
              onClick={async () => {
                if (!confirmDeleteWizardId) return;
                const wizardId = confirmDeleteWizardId;
                setConfirmDeleteWizardId(null);
                await performDeleteWizard(wizardId);
              }}
              className="px-3 py-1.5 rounded bg-red-600 text-white"
            >
              Delete
            </button>
          </div>
        }
      >
        <div className="text-sm text-gray-700">
          Delete this wizard and all its steps?
        </div>
      </Modal>
    </div>
  );
}

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

function RuleExtractorWrapper({ onRuleSaved }: { onRuleSaved: () => void }) {
  return (
    <div className="bg-white rounded-lg shadow border">
      <RuleExtractor onRuleSaved={onRuleSaved} />
    </div>
  );
}
