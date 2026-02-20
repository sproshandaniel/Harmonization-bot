import { useMemo, useState, useEffect } from "react";
import {
  Upload,
  FileText,
  Wand2,
  Filter,
  X,
  Edit3,
  Save,
} from "lucide-react";
import Modal from "../Components/modal";
import Editor from "@monaco-editor/react";
import yaml from "js-yaml";

function LoadingOverlay() {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-lg shadow-lg p-6 flex flex-col items-center">
        <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-3"></div>
        <p className="text-gray-700 font-semibold text-center">
          Extracting rules… please wait
        </p>
      </div>
    </div>
  );
}

type RuleResult = {
  yaml: string;
  confidence: number;
  category?: "code" | "design" | "template" | "wizard";
  subtags?: string[];
  duplicate_of?: string | null;
  similarity?: number | null;
  source_snippet?: string;
  status?: "new" | "approved" | "edited" | "discarded" | "saved";
  _severity?: string;
  _id?: string;
};

type RuleTestResult = {
  ok: boolean;
  passed: boolean;
  message: string;
  detail?: string;
};

type Project = {
  id: string;
  name: string;
  description?: string;
};

type AvailablePack = {
  name: string;
};

type RuleExtractorProps = {
  onRuleSaved?: () => void;
};

const MULTI_EXTRACT_TYPES = ["code", "design", "template"] as const;

export default function RuleExtractor({ onRuleSaved }: RuleExtractorProps) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [inputSource, setInputSource] = useState<"text" | "file">("text");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<RuleResult[]>([]);
  const [filter, setFilter] = useState<{ category?: string; q?: string }>({});
  const [ruleType, setRuleType] = useState<string>("code");
  const [multiRuleTypes, setMultiRuleTypes] = useState<string[]>(["code"]);
  const [wizardName, setWizardName] = useState<string>("");
  const [wizardDescription, setWizardDescription] = useState<string>("");
  const [wizardTotalSteps, setWizardTotalSteps] = useState<number>(3);
  const [wizardStepTitle, setWizardStepTitle] = useState<string>("");
  const [wizardStepDescription, setWizardStepDescription] = useState<string>("");
  const [wizardNextStepNo, setWizardNextStepNo] = useState<number>(1);
  const [maxRules, setMaxRules] = useState<number>(5);
  const [rulePackOptions, setRulePackOptions] = useState<string[]>([]);
  const [rulePack, setRulePack] = useState<string>("");
  const createdBy = localStorage.getItem("hb_user_email") || "name@zalaris.com";
  const [extractError, setExtractError] = useState<string | null>(null);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [wizardSaveError, setWizardSaveError] = useState<string | null>(null);

  // Projects (initialized with demo values)
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [loadingProjectRules, setLoadingProjectRules] = useState(false);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editorIdx, setEditorIdx] = useState<number | null>(null);
  const [editorValue, setEditorValue] = useState<string>("");
  const [editorError, setEditorError] = useState<string | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [noticeMessage, setNoticeMessage] = useState("");
  const [saveSuccessOpen, setSaveSuccessOpen] = useState(false);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [testCodeByIndex, setTestCodeByIndex] = useState<Record<number, string>>({});
  const [testResultByIndex, setTestResultByIndex] = useState<Record<number, RuleTestResult>>({});
  const [testingIndex, setTestingIndex] = useState<number | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);

  const filtered = useMemo(() => {
    return results
      .map((r, index) => ({ r, index }))
      .filter(({ r }) => {
      const matchesCat = filter.category ? r.category === filter.category : true;
      const matchesQuery = filter.q
        ? r.yaml.toLowerCase().includes(filter.q.toLowerCase())
        : true;
      return matchesCat && matchesQuery && r.status !== "discarded";
      });
  }, [results, filter]);

  const selectedProject = useMemo(
    () => projects.find((p) => p.id === selectedProjectId) || null,
    [projects, selectedProjectId]
  );
  const hasSourceInput = inputSource === "text" ? !!text.trim() : !!file;

  function showNotice(message: string) {
    setNoticeMessage(message);
    setNoticeOpen(true);
  }

  // --------- Load projects from backend ----------
  useEffect(() => {
    const loadProjects = async () => {
      try {
        setLoadingProjects(true);
        const res = await fetch("/api/projects");
        if (!res.ok) throw new Error(`Projects API failed (${res.status})`);
        const data: Project[] = await res.json();
        if (data && data.length > 0) {
          setProjects(data);
          setSelectedProjectId(data[0].id);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "Error loading projects.";
        showNotice(message);
      } finally {
        setLoadingProjects(false);
      }
    };
    loadProjects();
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const syncTheme = () => {
      setIsDarkMode(root.classList.contains("dark"));
    };
    syncTheme();
    const observer = new MutationObserver(syncTheme);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  // --------- Keep extractor results session-only ----------
  useEffect(() => {
    setLoadingProjectRules(false);
    setResults([]);
    setExpanded(new Set());
    setTestCodeByIndex({});
    setTestResultByIndex({});
    setWizardNextStepNo(1);
  }, [selectedProjectId]);

  // --------- Extract rules (backend only) ----------

  async function extractRules() {
    const nextErrors: Record<string, string> = {};
    const currentWizardSteps = results.filter(
      (r) => r.category === "wizard" && r.status !== "discarded"
    ).length;
    const derivedNextStepNo =
      ruleType === "wizard" ? currentWizardSteps + 1 : 1;

    if (!selectedProjectId) nextErrors.project = "Please select a project.";
    if (inputSource === "text" && !text.trim()) {
      nextErrors.text = "Please paste code or guideline text.";
    }
    if (inputSource === "file" && !file) {
      nextErrors.file = "Please select a file to upload.";
    }
    if (ruleType === "wizard" && !wizardName.trim()) {
      nextErrors.wizardName = "Please enter a wizard name.";
    }
    if (ruleType === "wizard" && !wizardDescription.trim()) {
      nextErrors.wizardDescription = "Please enter a wizard description.";
    }
    if (ruleType === "wizard" && wizardTotalSteps < 1) {
      nextErrors.wizardTotalSteps = "Please enter a total step count (min 1).";
    }
    if (ruleType === "wizard" && derivedNextStepNo > wizardTotalSteps) {
      nextErrors.wizardStepNo = "All wizard steps have already been extracted.";
    }
    if (ruleType === "wizard" && !wizardStepTitle.trim()) {
      nextErrors.wizardStepTitle = "Please enter a step title.";
    }
    if (ruleType === "wizard" && !wizardStepDescription.trim()) {
      nextErrors.wizardStepDescription = "Please enter a step description.";
    }
    if (ruleType === "multi" && multiRuleTypes.length === 0) {
      nextErrors.multiRuleTypes = "Please select at least one type.";
    }

    if (Object.keys(nextErrors).length > 0) {
      setFormErrors(nextErrors);
      return;
    }
    setFormErrors({});
    setLoading(true);
    setExtractError(null);

    try {
      const form = new FormData();
      if (inputSource === "file" && file) {
        form.append("file", file);
      } else {
        form.append("text", text);
      }
      form.append("rule_type", ruleType === "multi" ? "code" : ruleType);
      if (ruleType === "multi") {
        form.append("rule_types", multiRuleTypes.join(","));
      }
      const effectiveMaxRules = ruleType === "wizard" ? 1 : maxRules;
      form.append("max_rules", String(effectiveMaxRules));
      if (ruleType === "template" || (ruleType === "multi" && multiRuleTypes.includes("template"))) {
        form.append("template_use_ai", "true");
      }
      if (ruleType === "wizard") {
        form.append("wizard_name", wizardName.trim());
        form.append("wizard_description", wizardDescription.trim());
        form.append("wizard_total_steps", String(wizardTotalSteps));
        form.append("wizard_step_no", String(derivedNextStepNo));
        form.append("wizard_step_title", wizardStepTitle.trim());
        form.append("wizard_step_description", wizardStepDescription.trim());
      }
      form.append("rule_pack", rulePack);
      form.append("created_by", createdBy);
      form.append("project_id", selectedProjectId);

      const res = await fetch(
        inputSource === "file" ? "/api/extract-from-document" : "/api/extract-rule",
        { method: "POST", body: form }
      );

      if (res.ok) {
        const data = await res.json();
        const rawRules: RuleResult[] = Array.isArray(data)
          ? data
          : data.rules
          ? data.rules
          : data.yaml || data.id
          ? [data]
          : [];

        if (rawRules.length > 0) {
          const rules = rawRules.map((r) => {
            if (ruleType === "wizard") {
              const wizardYaml = mergeWizardMeta(r.yaml, derivedNextStepNo);
              return tagDerived({ ...r, yaml: wizardYaml, category: "wizard" });
            }
            if (ruleType === "multi") {
              return tagDerived({ ...r });
            }
            const forcedYaml = forceTypeInYaml(r.yaml, ruleType);
            return tagDerived({ ...r, yaml: forcedYaml, category: ruleType as RuleResult["category"] });
          });
          const newRules: RuleResult[] = rules.map(
            (r): RuleResult => ({ ...r, status: "new" })
          );
          if (ruleType === "wizard") {
            setResults((prev) => [...prev, ...newRules]);
          } else {
            setResults(newRules);
          }
          if (ruleType === "wizard") {
            setWizardNextStepNo(derivedNextStepNo + 1);
            setWizardStepTitle("");
            setWizardStepDescription("");
          }
          return;
        }

        setResults([]);
        setExtractError("No rules returned from the backend.");
        return;
      }

      const errText = await res.text();
      setExtractError(
        `Extraction failed (${res.status}). ${errText || "Backend error."}`
      );
    } catch (e: any) {
      setExtractError(e?.message || "Extraction failed. Backend not reachable.");
    } finally {
      setLoading(false);
    }
  }

  function discardRule(idx: number) {
    setResults((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, status: "discarded" } : r))
    );
  }

  function openEditor(idx: number) {
    const rule = results[idx];
    setEditorIdx(idx);
    setEditorValue(rule.yaml);
    setEditorError(null);
    setEditorOpen(true);
  }

  function onEditorChange(next?: string) {
    const val = next ?? "";
    setEditorValue(val);
    try {
      yaml.load(val);
      setEditorError(null);
    } catch (err: any) {
      setEditorError(err?.message || "Invalid YAML");
    }
  }

  function saveEditor() {
    if (editorError || editorIdx === null) return;
    setResults((prev) =>
      prev.map((r, i) =>
        i === editorIdx
          ? tagDerived({ ...r, yaml: editorValue, status: "edited" })
          : r
      )
    );
    setEditorOpen(false);
  }

  useEffect(() => {
    const loadRulePackOptions = async () => {
      try {
        const optionsEndpoint =
          ruleType === "multi"
            ? "/api/rule-pack-options/all"
            : `/api/rule-pack-options?rule_type=${encodeURIComponent(ruleType)}`;
        const [optionsRes, packsRes] = await Promise.all([
          fetch(optionsEndpoint),
          fetch("/api/packs"),
        ]);
        if (!optionsRes.ok) {
          throw new Error(`Rule pack options API failed (${optionsRes.status})`);
        }
        if (!packsRes.ok) {
          throw new Error(`Rule packs API failed (${packsRes.status})`);
        }
        const optionsData = await optionsRes.json();
        const packsData = await packsRes.json();
        const typeOptions: string[] =
          ruleType === "multi"
            ? Array.isArray(optionsData?.items)
              ? optionsData.items.map((x: any) => String(x.pack_name || "").trim()).filter(Boolean)
              : []
            : Array.isArray(optionsData?.options)
            ? optionsData.options
            : [];
        const availablePacks: string[] = Array.isArray(packsData?.packs)
          ? (packsData.packs as AvailablePack[]).map((p) => String(p.name || "").trim()).filter(Boolean)
          : [];

        const merged = Array.from(new Set([...typeOptions, ...availablePacks])).sort((a, b) =>
          a.localeCompare(b)
        );
        setRulePackOptions(merged);
        setRulePack((prev) => {
          if (prev && merged.includes(prev)) return prev;
          return merged[0] || "";
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load rule pack options.";
        showNotice(message);
        setRulePackOptions([]);
        setRulePack("");
      }
    };
    void loadRulePackOptions();
  }, [ruleType]);

  useEffect(() => {
    if (ruleType === "template") {
      setMaxRules(1);
    }
  }, [ruleType]);

  useEffect(() => {
    if (ruleType !== "multi") {
      return;
    }
    setMultiRuleTypes((prev) => (prev.length > 0 ? prev : ["code"]));
  }, [ruleType]);

  useEffect(() => {
    if (ruleType !== "wizard") {
      setWizardName("");
      setWizardDescription("");
      setWizardTotalSteps(3);
      setWizardStepTitle("");
      setWizardStepDescription("");
      setWizardNextStepNo(1);
    }
  }, [ruleType]);

  async function saveSingleRule(idx: number) {
    if (!selectedProjectId) {
      showNotice("Please select a project.");
      return;
    }
    const rule = results[idx];
    try {
      const res = await fetch(`/api/projects/${selectedProjectId}/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          yaml: rule.yaml,
          confidence: rule.confidence,
          category: rule.category,
          _id: rule._id,
          _severity: rule._severity,
          created_by: createdBy,
          rule_pack: rulePack || "manual",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setResults((prev) => prev.filter((_, i) => i !== idx));
      setSaveSuccessMessage("Rule saved successfully.");
      setSaveSuccessOpen(true);
      onRuleSaved?.();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Save failed";
      showNotice(message);
    }
  }

  async function saveWizard() {
    const nextErrors: Record<string, string> = {};
    if (!selectedProjectId) nextErrors.project = "Please select a project.";
    if (!wizardName.trim()) nextErrors.wizardName = "Please enter a wizard name.";
    if (!wizardDescription.trim()) nextErrors.wizardDescription = "Please enter a wizard description.";
    if (wizardTotalSteps < 1) nextErrors.wizardTotalSteps = "Please enter a total step count (min 1).";

    const wizardSteps = results.filter(
      (r) => r.category === "wizard" && r.status !== "discarded"
    );
    if (wizardSteps.length === 0) {
      nextErrors.wizardSteps = "Extract at least one wizard step before saving.";
    }

    if (Object.keys(nextErrors).length > 0) {
      setFormErrors((prev) => ({ ...prev, ...nextErrors }));
      return;
    }

    try {
      setWizardSaveError(null);
      const res = await fetch("/api/wizards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: selectedProjectId,
          wizard_name: wizardName.trim(),
          wizard_description: wizardDescription.trim(),
          total_steps: wizardTotalSteps,
          rule_pack: rulePack || "wizard",
          steps: wizardSteps.map((r) => ({
            yaml: r.yaml,
            confidence: r.confidence,
            category: r.category,
            _id: r._id,
            _severity: r._severity,
          })),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSaveSuccessMessage(
        `Wizard saved with id ${data?.wizard_id || "unknown"}.`
      );
      setSaveSuccessOpen(true);
      setResults([]);
      setWizardNextStepNo(1);
      setFormErrors((prev) => ({ ...prev, wizardSteps: "" }));
      onRuleSaved?.();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Save failed";
      setWizardSaveError(message);
    }
  }

  async function testRule(idx: number) {
    const rule = results[idx];
    const testCode = (testCodeByIndex[idx] || "").trim();
    if (!testCode) {
      setTestResultByIndex((prev) => ({
        ...prev,
        [idx]: { ok: false, passed: false, message: "Enter code to test." },
      }));
      return;
    }
    try {
      setTestingIndex(idx);
      const res = await fetch("/api/rules/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rule_yaml: rule.yaml,
          code: testCode,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as RuleTestResult;
      setTestResultByIndex((prev) => ({ ...prev, [idx]: data }));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Test failed";
      setTestResultByIndex((prev) => ({
        ...prev,
        [idx]: { ok: false, passed: false, message },
      }));
    } finally {
      setTestingIndex(null);
    }
  }

  // --- Update severity both in YAML and derived fields ----------------

  function updateRuleSeverity(idx: number, newSeverity: string) {
    setResults((prev) =>
      prev.map((r, i) => {
        if (i !== idx) return r;

        try {
          const obj: any = yaml.load(r.yaml) || {};
          obj.severity = newSeverity;
          const newYaml = yaml.dump(obj, { lineWidth: 80 });

          const updated: RuleResult = {
            ...r,
            yaml: newYaml,
            status: r.status === "approved" ? "approved" : "edited",
          };

          return tagDerived(updated);
        } catch {
          showNotice("Failed to update severity in YAML.");
          return {
            ...r,
            _severity: newSeverity,
            status: "edited",
          };
        }
      })
    );
  }

  function tagDerived(r: RuleResult): RuleResult {
    try {
      const obj: any = yaml.load(r.yaml);
      const normalizedSubtags = (() => {
        const raw = obj?.subtags;
        if (Array.isArray(raw)) {
          return raw
            .map((x: unknown) => String(x || "").trim().toLowerCase())
            .filter((x: string) => ["code", "naming", "performance"].includes(x));
        }
        return [];
      })();
      return {
        ...r,
        _id: obj?.id,
        _severity: obj?.severity,
        category: obj?.type ?? r.category,
        subtags: normalizedSubtags,
      };
    } catch {
      return r;
    }
  }

  function forceTypeInYaml(yamlText: string, forcedType: string): string {
    try {
      const obj: any = yaml.load(yamlText) || {};
      obj.type = forcedType;
      return yaml.dump(obj, { lineWidth: 120 });
    } catch {
      return yamlText;
    }
  }

  function mergeWizardMeta(yamlText: string, stepNo: number): string {
    try {
      const obj: any = yaml.load(yamlText) || {};
      obj.type = "wizard";
      const wizard = typeof obj.wizard === "object" && obj.wizard ? obj.wizard : {};
      wizard.wizard_name = wizardName.trim();
      wizard.wizard_description = wizardDescription.trim();
      wizard.total_steps = wizardTotalSteps;
      wizard.step_no = stepNo;
      wizard.step_title = wizardStepTitle.trim();
      wizard.step_description = wizardStepDescription.trim();
      obj.wizard = wizard;
      if (!obj.title) obj.title = wizardStepTitle.trim();
      if (!obj.description) obj.description = wizardStepDescription.trim();
      return yaml.dump(obj, { lineWidth: 120 });
    } catch {
      return yamlText;
    }
  }

  // ---------------- RENDER ----------------
  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      <div className="flex flex-1">
        {/* LEFT PANEL */}
        <aside className="w-full lg:w-[36%] border-r bg-white p-6 space-y-4">
          <div className="flex items-center gap-2 text-indigo-700 font-semibold">
            <Wand2 size={18} />
            <span>Rule Extraction</span>
          </div>

          {/* Project & Rule Type */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Project
              </label>
              <select
                value={selectedProjectId}
                onChange={(e) => {
                  setSelectedProjectId(e.target.value);
                  setFormErrors((prev) => ({ ...prev, project: "" }));
                }}
                className="border rounded w-full px-2 py-1 text-sm text-gray-700 focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">
                  {loadingProjects ? "Loading projects…" : "Select a project"}
                </option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
              {selectedProject && selectedProject.description && (
                <p className="mt-1 text-xs text-gray-500 line-clamp-2">
                  {selectedProject.description}
                </p>
              )}
              {formErrors.project && (
                <p className="mt-1 text-xs text-red-600">{formErrors.project}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Select Rule Type
              </label>
              <select
                value={ruleType}
                onChange={(e) => setRuleType(e.target.value)}
                className="border rounded w-full px-2 py-1 text-sm text-gray-700 focus:ring-2 focus:ring-indigo-500"
              >
                <option value="code">Code</option>
                <option value="design">Design</option>
                <option value="template">Template</option>
                <option value="multi">Multi Type</option>
                <option value="wizard">Wizard</option>
              </select>
            </div>
          </div>

          {ruleType === "multi" && (
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Multi Rule Types
              </label>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {MULTI_EXTRACT_TYPES.map((t) => (
                  <label key={t} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={multiRuleTypes.includes(t)}
                      onChange={(e) =>
                        setMultiRuleTypes((prev) =>
                          e.target.checked
                            ? Array.from(new Set([...prev, t]))
                            : prev.filter((x) => x !== t)
                        )
                      }
                    />
                    <span className="capitalize">{t}</span>
                  </label>
                ))}
              </div>
              {formErrors.multiRuleTypes && (
                <p className="mt-1 text-xs text-red-600">{formErrors.multiRuleTypes}</p>
              )}
            </div>
          )}

          {/* Rule Pack + Max Rules */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Select Rule Pack
              </label>
              <select
                value={rulePack}
                onChange={(e) => setRulePack(e.target.value)}
                className="border rounded w-full px-2 py-1 text-sm text-gray-700 focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">-- Choose Pack --</option>
                {rulePackOptions.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                {ruleType === "wizard" ? "Total Steps" : "Max Rules"}
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={ruleType === "wizard" ? wizardTotalSteps : maxRules}
                disabled={ruleType === "template"}
                onChange={(e) => {
                  if (ruleType === "template") return;
                  const raw = Number(e.target.value);
                  if (Number.isNaN(raw)) return;
                  if (ruleType === "wizard") {
                    setWizardTotalSteps(Math.max(1, Math.min(20, raw)));
                    return;
                  }
                  setMaxRules(Math.max(1, Math.min(10, raw)));
                }}
                className="border rounded w-full px-2 py-1 text-sm text-gray-700 focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-100 disabled:text-gray-500 disabled:cursor-not-allowed"
              />
            </div>
          </div>

          {ruleType === "wizard" && (
            <>
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">
                  Wizard Name
                </label>
                <input
                  className="border rounded w-full px-2 py-1 text-sm text-gray-700 focus:ring-2 focus:ring-indigo-500"
                  value={wizardName}
                  onChange={(e) => {
                    setWizardName(e.target.value);
                    setFormErrors((prev) => ({ ...prev, wizardName: "" }));
                  }}
                  placeholder="e.g. ABAP Factory Pattern Wizard"
                />
                {formErrors.wizardName && (
                  <p className="mt-1 text-xs text-red-600">{formErrors.wizardName}</p>
                )}
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">
                  Wizard Description
                </label>
                <textarea
                  className="border rounded w-full px-2 py-1 text-sm text-gray-700 focus:ring-2 focus:ring-indigo-500"
                  value={wizardDescription}
                  onChange={(e) => {
                    setWizardDescription(e.target.value);
                    setFormErrors((prev) => ({ ...prev, wizardDescription: "" }));
                  }}
                  placeholder="Short description of this wizard"
                />
                {formErrors.wizardDescription && (
                  <p className="mt-1 text-xs text-red-600">{formErrors.wizardDescription}</p>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1">
                    Step Title (Step {wizardNextStepNo})
                  </label>
                  <input
                    className="border rounded w-full px-2 py-1 text-sm text-gray-700 focus:ring-2 focus:ring-indigo-500"
                    value={wizardStepTitle}
                    onChange={(e) => {
                      setWizardStepTitle(e.target.value);
                      setFormErrors((prev) => ({ ...prev, wizardStepTitle: "" }));
                    }}
                    placeholder="Short step title"
                  />
                  {formErrors.wizardStepTitle && (
                    <p className="mt-1 text-xs text-red-600">{formErrors.wizardStepTitle}</p>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1">
                    Step Description
                  </label>
                  <input
                    className="border rounded w-full px-2 py-1 text-sm text-gray-700 focus:ring-2 focus:ring-indigo-500"
                    value={wizardStepDescription}
                    onChange={(e) => {
                      setWizardStepDescription(e.target.value);
                      setFormErrors((prev) => ({ ...prev, wizardStepDescription: "" }));
                    }}
                    placeholder="Short step description"
                  />
                  {formErrors.wizardStepDescription && (
                    <p className="mt-1 text-xs text-red-600">{formErrors.wizardStepDescription}</p>
                  )}
                </div>
              </div>
              {formErrors.wizardTotalSteps && (
                <p className="text-xs text-red-600">{formErrors.wizardTotalSteps}</p>
              )}
              {formErrors.wizardStepNo && (
                <p className="text-xs text-red-600">{formErrors.wizardStepNo}</p>
              )}
            </>
          )}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">
              Input Source
            </label>
            <div className="inline-flex rounded-md border border-gray-300 bg-gray-50 p-1">
              <button
                type="button"
                onClick={() => {
                  setInputSource("text");
                  setFile(null);
                  setFormErrors((prev) => ({ ...prev, file: "", text: "" }));
                }}
                className={`px-3 py-1 text-xs rounded ${
                  inputSource === "text" ? "bg-indigo-600 text-white" : "text-gray-700"
                }`}
              >
                Paste Text
              </button>
              <button
                type="button"
                onClick={() => {
                  setInputSource("file");
                  setText("");
                  setFormErrors((prev) => ({ ...prev, file: "", text: "" }));
                }}
                className={`px-3 py-1 text-xs rounded ${
                  inputSource === "file" ? "bg-indigo-600 text-white" : "text-gray-700"
                }`}
              >
                Upload File
              </button>
            </div>
          </div>
          {/* Code / guideline editor */}
          <div className="flex items-center justify-between">
            <label className="block text-sm text-gray-600 mb-1">
              Paste code or guideline text
            </label>
            <button
              type="button"
              onClick={() => setText("")}
              disabled={inputSource !== "text"}
              className="text-xs px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50"
            >
              Clear Input
            </button>
          </div>
          <div className={`border rounded overflow-hidden ${inputSource !== "text" ? "opacity-60" : ""}`}>
            <Editor
              height="500px"
              defaultLanguage="plaintext"
              theme={isDarkMode ? "vs-dark" : "vs-light"}
              value={text}
              onChange={(val) => {
                setText(val ?? "");
                if (val?.trim()) setFormErrors((prev) => ({ ...prev, text: "" }));
              }}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                lineNumbers: "on",
                automaticLayout: true,
                scrollBeyondLastLine: false,
                wordWrap: "on",
                padding: { top: 12, bottom: 12 },
                readOnly: inputSource !== "text",
              }}
            />
          </div>
          {formErrors.text && (
            <p className="text-xs text-red-600">{formErrors.text}</p>
          )}

          {/* Upload */}
          <div className="flex items-center gap-3">
            <label className="block text-sm text-gray-600">
              Upload document (PDF/DOCX/TXT/MD)
            </label>
          </div>
          <div className="flex items-center gap-3">
            <label className={`inline-flex items-center px-3 py-2 rounded border ${
              inputSource === "file"
                ? "bg-gray-100 cursor-pointer hover:bg-gray-200"
                : "bg-gray-100/70 text-gray-400 cursor-not-allowed"
            }`}>
              <Upload size={16} className="mr-2" /> Choose File
              <input
                type="file"
                className="hidden"
                accept=".pdf,.docx,.txt,.md"
                disabled={inputSource !== "file"}
                onChange={(e) => {
                  setFile(e.target.files?.[0] || null);
                  setFormErrors((prev) => ({ ...prev, file: "" }));
                }}
              />
            </label>
            <span className="text-sm text-gray-600">
              {file ? file.name : "No file selected"}
            </span>
          </div>
          {formErrors.file && (
            <p className="text-xs text-red-600">{formErrors.file}</p>
          )}

          {/* Extract Button */}
          <button
            onClick={extractRules}
            disabled={loading || !selectedProjectId || !hasSourceInput}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-60"
          >
            <Wand2 size={16} />
            {loading
              ? "Extracting…"
              : ruleType === "wizard"
              ? "Extract Step"
              : "Extract Rule"}
          </button>
        </aside>

        {/* RIGHT PANEL */}
        <main className="flex-1 p-6">
          {extractError && (
            <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {extractError}
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-2 text-gray-700">
              <FileText size={18} />
              <span className="font-semibold">Extracted Rules</span>
              <span className="text-sm text-gray-500">
                ({filtered.length})
              </span>
              {selectedProject && (
                <span className="ml-2 text-xs text-gray-500">
                  for project: <strong>{selectedProject.name}</strong>
                </span>
              )}
              {loadingProjectRules && (
                <span className="ml-2 text-xs text-indigo-500">
                  Loading project rules…
                </span>
              )}
              {ruleType === "wizard" && (
                <span className="ml-2 text-xs text-gray-500">
                  Next step: {wizardNextStepNo} / {wizardTotalSteps}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {ruleType === "wizard" &&
                results.some(
                  (r) => r.category === "wizard" && r.status !== "discarded"
                ) && (
                  <div className="flex flex-col items-end gap-1">
                    <button
                      onClick={saveWizard}
                      className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-emerald-600 text-white hover:bg-emerald-700"
                    >
                      <Save size={14} />
                      Save Wizard
                    </button>
                    {formErrors.wizardSteps && (
                      <span className="text-xs text-red-600">{formErrors.wizardSteps}</span>
                    )}
                    {wizardSaveError && (
                      <span className="text-xs text-red-600">{wizardSaveError}</span>
                    )}
                  </div>
                )}
              <div className="flex items-center gap-2 border rounded px-2 py-1 bg-white">
                <Filter size={16} />
                <select
                  className="text-sm outline-none"
                  value={filter.category || ""}
                  onChange={(e) =>
                    setFilter((f) => ({
                      ...f,
                      category: e.target.value || undefined,
                    }))
                  }
                >
                  <option value="">All Categories</option>
                  <option value="code">Code</option>
                  <option value="design">Design</option>
                  <option value="template">Template</option>
                  <option value="wizard">Wizard</option>
                </select>
              </div>
              <input
                className="border rounded px-3 py-1 text-sm"
                placeholder="Search in YAML…"
                onChange={(e) =>
                  setFilter((f) => ({ ...f, q: e.target.value }))
                }
              />
            </div>
          </div>

          {/* Rules grid */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            {filtered.map(({ r: rule, index: resultIdx }) => {
              const isExpanded = expanded.has(resultIdx);
              const confidencePct = Math.round(
                (rule.confidence ?? 0) * 100
              );
              let selectorWarning = "";
              let goodExampleCode = "";
              try {
                const parsed: any = yaml.load(rule.yaml);
                const selector = parsed?.selector;
                const pattern =
                  typeof selector === "string"
                    ? selector.trim()
                    : String(selector?.pattern || "").trim();
                const generic = new Set([
                  "",
                  "template_snippet",
                  "wizard_step",
                  "wizard",
                  "template",
                  "abap rule",
                  "abap template",
                ]);
                if (generic.has(pattern.toLowerCase())) {
                  selectorWarning = "Selector is missing or too generic.";
                }
                const example = parsed?.example;
                goodExampleCode =
                  typeof example === "object" && example
                    ? String(
                        example.good ||
                          example.good_code ||
                          example.example_good_code ||
                          ""
                      ).trim()
                    : "";
              } catch {
                selectorWarning = "Selector could not be parsed.";
              }

              return (
                <div
                  key={`${rule._id || "rule"}-${resultIdx}`}
                  className="border rounded-xl bg-white shadow-sm flex flex-col overflow-hidden"
                >
                  <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-gray-900">
                          {rule._id || `Rule ${resultIdx + 1}`}
                        </span>
                        {rule.category && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">
                            {rule.category}
                          </span>
                        )}
                        {rule.category === "code" &&
                          Array.isArray(rule.subtags) &&
                          rule.subtags
                            .filter((tag) => tag !== "code")
                            .map((tag) => (
                              <span
                                key={`${rule._id || resultIdx}-${tag}`}
                                className="text-xs px-2 py-0.5 rounded-full bg-sky-100 text-sky-700"
                              >
                                {tag}
                              </span>
                            ))}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-gray-500">
                        <div className="flex items-center gap-1">
                          <span>Severity</span>
                          <select
                            value={rule._severity || "MAJOR"}
                            onChange={(e) =>
                              updateRuleSeverity(resultIdx, e.target.value)
                            }
                            className="border rounded px-2 py-0.5 bg-white text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          >
                            <option value="MAJOR">MAJOR</option>
                            <option value="MINOR">MINOR</option>
                            <option value="INFO">INFO</option>
                          </select>
                        </div>
                        <div className="flex items-center gap-1">
                          <span>Confidence</span>
                          <span className="font-semibold text-gray-700">
                            {confidencePct}%
                          </span>
                          <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-indigo-500"
                              style={{ width: `${confidencePct}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col items-end gap-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          rule.status === "approved"
                            ? "bg-green-100 text-green-700"
                            : rule.status === "saved"
                            ? "bg-emerald-100 text-emerald-700"
                            : rule.status === "edited"
                            ? "bg-yellow-100 text-yellow-700"
                            : rule.status === "discarded"
                            ? "bg-gray-200 text-gray-600"
                            : "bg-blue-100 text-blue-700"
                        }`}
                      >
                        {rule.status || "new"}
                      </span>
                      <button
                        onClick={() => {
                          setExpanded((prev) => {
                            const next = new Set(prev);
                            if (next.has(resultIdx)) next.delete(resultIdx);
                            else next.add(resultIdx);
                            return next;
                          });
                        }}
                        className="text-xs text-gray-500 hover:text-gray-700"
                      >
                        {isExpanded ? "Hide details" : "Show details"}
                      </button>
                    </div>
                  </div>

                  <div className="p-4 space-y-3">
                    <div className="relative">
                      <pre
                        className={`bg-gray-900 text-gray-100 text-xs rounded-md p-3 overflow-auto transition-all ${
                          isExpanded ? "max-h-72" : "max-h-32"
                        }`}
                      >
                        {rule.yaml}
                      </pre>
                    </div>
                    {selectorWarning && (
                      <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                        {selectorWarning}
                      </div>
                    )}

                    {rule.source_snippet && (
                      <div className="text-xs text-gray-600 space-y-1">
                        <div className="font-semibold text-gray-700">
                          Source snippet
                        </div>
                        <pre className="bg-gray-50 border rounded p-2 max-h-32 overflow-auto">
                          {rule.source_snippet}
                        </pre>
                      </div>
                    )}

                    {rule.category !== "template" &&
                      rule.category !== "wizard" &&
                      goodExampleCode && (
                        <div className="text-xs text-gray-700 space-y-1">
                          <div className="font-semibold text-gray-700">
                            Good Code Example
                          </div>
                          <pre className="bg-green-50 border border-green-200 rounded p-2 max-h-40 overflow-auto text-[11px]">
                            {goodExampleCode}
                          </pre>
                        </div>
                      )}

                    {rule.category !== "template" && rule.category !== "wizard" && (
                      <div className="space-y-2">
                        <div className="text-xs font-semibold text-gray-700">Test Against Code</div>
                        <textarea
                          className="w-full border rounded p-2 text-xs font-mono h-24"
                          placeholder="Paste code to validate against this rule"
                          value={testCodeByIndex[resultIdx] || ""}
                          onChange={(e) =>
                            setTestCodeByIndex((prev) => ({
                              ...prev,
                              [resultIdx]: e.target.value,
                            }))
                          }
                        />
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => testRule(resultIdx)}
                            disabled={testingIndex === resultIdx}
                            className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-60"
                          >
                            {testingIndex === resultIdx ? "Testing..." : "Test Rule"}
                          </button>
                          {testResultByIndex[resultIdx] && (
                            <span
                              className={`text-xs px-2 py-1 rounded ${
                                testResultByIndex[resultIdx].passed
                                  ? "bg-green-100 text-green-700"
                                  : "bg-red-100 text-red-700"
                              }`}
                            >
                              {testResultByIndex[resultIdx].passed ? "Pass" : "Fail"}
                            </span>
                          )}
                        </div>
                        {testResultByIndex[resultIdx] && (
                          <div
                            className={`text-xs rounded px-2 py-1 ${
                              testResultByIndex[resultIdx].passed
                                ? "bg-green-50 text-green-700 border border-green-200"
                                : "bg-red-50 text-red-700 border border-red-200"
                            }`}
                          >
                            {testResultByIndex[resultIdx].message}
                          </div>
                        )}
                      </div>
                    )}

                    <div className="flex items-center justify-end gap-2 pt-2 border-t border-gray-100">
                      {rule.category !== "wizard" && (
                        <button
                          onClick={() => saveSingleRule(resultIdx)}
                          className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-indigo-600 text-white hover:bg-indigo-700"
                        >
                          <Save size={14} />
                          Save Rule
                        </button>
                      )}
                      <button
                        onClick={() => openEditor(resultIdx)}
                        className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded border border-gray-300 hover:bg-gray-50"
                      >
                        <Edit3 size={14} />
                        Edit YAML
                      </button>
                      <button
                        onClick={() => discardRule(resultIdx)}
                        className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-red-50 text-red-600 hover:bg-red-100"
                      >
                        <X size={14} />
                        Discard
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </main>
      </div>

      {/* YAML Editor Modal */}
      <Modal
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        title="Edit Rule YAML"
        footer={
          <div className="flex items-center justify-between">
            <div
              className={`text-xs ${
                editorError ? "text-red-600" : "text-green-700"
              }`}
            >
              {editorError ? `YAML error: ${editorError}` : "Valid YAML"}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setEditorOpen(false)}
                className="px-3 py-1.5 rounded border"
              >
                Cancel
              </button>
              <button
                onClick={saveEditor}
                disabled={!!editorError}
                className="px-3 py-1.5 rounded bg-indigo-600 text-white disabled:opacity-60"
              >
                Save
              </button>
            </div>
          </div>
        }
      >
        <div className="h-[60vh]">
          <Editor
            height="100%"
            defaultLanguage="yaml"
            theme={isDarkMode ? "vs-dark" : "vs-light"}
            value={editorValue}
            onChange={onEditorChange}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              scrollBeyondLastLine: false,
              wordWrap: "on",
            }}
          />
        </div>
      </Modal>

      <Modal
        open={saveSuccessOpen}
        onClose={() => setSaveSuccessOpen(false)}
        title="Success"
        footer={
          <div className="flex justify-end">
            <button
              onClick={() => setSaveSuccessOpen(false)}
              className="px-3 py-1.5 rounded bg-indigo-600 text-white"
            >
              OK
            </button>
          </div>
        }
      >
        <div className="text-sm text-gray-700">{saveSuccessMessage}</div>
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

      {loading && <LoadingOverlay />}
    </div>
  );
}



