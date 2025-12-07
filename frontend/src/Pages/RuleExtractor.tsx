import { useMemo, useState, useEffect } from "react";
import {
  Upload,
  FileText,
  Wand2,
  Filter,
  Check,
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
  category?: "code" | "design" | "naming" | "performance" | "template";
  duplicate_of?: string | null;
  similarity?: number | null;
  source_snippet?: string;
  status?: "new" | "approved" | "edited" | "discarded";
  _severity?: string;
  _id?: string;
};

type Project = {
  id: string;
  name: string;
  description?: string;
};

export default function RuleExtractor() {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false); // extraction loading
  const [results, setResults] = useState<RuleResult[]>([]);
  const [pack, setPack] = useState<string>("abap-core-standards");
  const [filter, setFilter] = useState<{ category?: string; q?: string }>({});
  const [ruleType, setRuleType] = useState<string>("code");
  const [rulePackOptions, setRulePackOptions] = useState<string[]>([]);
  const [rulePack, setRulePack] = useState<string>("");
  const [user, setUser] = useState<string>("Architect User");

  // NEW: project state
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [loadingProjectRules, setLoadingProjectRules] = useState(false);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editorIdx, setEditorIdx] = useState<number | null>(null);
  const [editorValue, setEditorValue] = useState<string>("");
  const [editorError, setEditorError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const filtered = useMemo(() => {
    return results.filter((r) => {
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

  // --------- NEW: load projects on mount ----------
  useEffect(() => {
    const loadProjects = async () => {
      try {
        setLoadingProjects(true);
        const res = await fetch("/api/projects");
        if (!res.ok) {
          throw new Error(`Failed to load projects (${res.status})`);
        }
        const data: Project[] = await res.json();
        setProjects(data || []);
        if (data && data.length > 0) {
          setSelectedProjectId(data[0].id);
        }
      } catch (err) {
        console.error("Error loading projects", err);
      } finally {
        setLoadingProjects(false);
      }
    };
    loadProjects();
  }, []);

  // --------- NEW: load rules when project changes ----------
  useEffect(() => {
    const loadRulesForProject = async () => {
      if (!selectedProjectId) {
        setResults([]);
        return;
      }
      try {
        setLoadingProjectRules(true);
        const res = await fetch(`/api/projects/${selectedProjectId}/rules`);
        if (!res.ok) {
          throw new Error(`Failed to load rules for project (${res.status})`);
        }
        const data = await res.json();
        // assuming API returns { rules: [...] } or just [...]
        const rawRules: RuleResult[] = Array.isArray(data)
          ? data
          : data.rules || [];
        const tagged = rawRules.map(tagDerived);
        setResults(tagged.map((r) => ({ status: "approved", ...r })));
      } catch (err) {
        console.error("Error loading project rules", err);
        // do not wipe previous results if fetch fails
      } finally {
        setLoadingProjectRules(false);
      }
    };

    loadRulesForProject();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  async function extractRules() {
    if (!selectedProjectId) {
      alert("Please select a project before extracting rules.");
      return;
    }

    setLoading(true);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      else form.append("text", text);
      form.append("rule_type", ruleType);
      form.append("rule_pack", rulePack);
      form.append("created_by", user);
      // NEW: associate extraction with project
      form.append("project_id", selectedProjectId);

      const res = await fetch(
        file ? "/api/extract-from-document" : "/api/extract-rule",
        { method: "POST", body: form }
      );
      if (!res.ok) throw new Error(`Backend responded with ${res.status}`);
      const data = await res.json();
      const rules: RuleResult[] = (data.rules ? data.rules : [data]).map(
        tagDerived
      );
      setResults(rules.map((r) => ({ status: "new", ...r })));
    } catch (e) {
      console.error(e);
      alert("Extraction failed. Check backend logs.");
    } finally {
      setLoading(false);
    }
  }

  function approveRule(idx: number) {
    setResults((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, status: "approved" } : r))
    );
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

  function getRulePacksForType(type: string): string[] {
    switch (type) {
      case "code":
        return ["abap-core-safety", "abap-db-standards", "abap-unit-tests"];
      case "design":
        return ["architecture-guidelines", "design-patterns"];
      case "naming":
        return ["naming-standards", "package-prefixes"];
      case "performance":
        return ["performance-optimizations", "sql-guidelines"];
      case "template":
        return ["code-templates", "developer-snippets"];
      default:
        return ["generic"];
    }
  }

  useEffect(() => {
    setRulePackOptions(getRulePacksForType(ruleType));
    setRulePack("");
  }, [ruleType]);

  async function saveApprovedToPack() {
    const approved = results.filter(
      (r) => r.status === "approved" || r.status === "edited"
    );
    if (!approved.length) return alert("No approved rules to save.");
    try {
      const res = await fetch(`/api/packs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: pack,
          status: "draft",
          // you might also want to send project_id here if packs are per-project
          project_id: selectedProjectId || undefined,
          rules: approved.map((r) => {
            try {
              return yaml.load(r.yaml);
            } catch {
              return { _raw: r.yaml };
            }
          }),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      alert(`Saved ${approved.length} rule(s) to pack "${pack}".`);
    } catch (e: any) {
      alert(`Save failed: ${e.message}`);
    }
  }

  function tagDerived(r: RuleResult): RuleResult {
    try {
      const obj: any = yaml.load(r.yaml);
      return {
        ...r,
        _id: obj?.id,
        _severity: obj?.severity,
        category: obj?.type ?? r.category,
      };
    } catch {
      return r;
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

          {/* NEW: Project selector */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Project
              </label>
              <select
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
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
                <option value="naming">Naming</option>
                <option value="performance">Performance</option>
                <option value="template">Template</option>
              </select>
            </div>
          </div>

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
                {rulePackOptions.map((pack) => (
                  <option key={pack} value={pack}>
                    {pack}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                User
              </label>
              <input
                className="border rounded w-full px-2 py-1 text-sm text-gray-700 focus:ring-2 focus:ring-indigo-500"
                value={user}
                onChange={(e) => setUser(e.target.value)}
              />
            </div>
          </div>

          <label className="block text-sm text-gray-600 mb-1">
            Paste code or guideline text
          </label>
          <div className="border rounded overflow-hidden">
            <Editor
              height="500px"
              defaultLanguage="plaintext"
              theme="vs-light"
              value={text}
              onChange={(val) => setText(val ?? "")}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                lineNumbers: "on",
                automaticLayout: true,
                scrollBeyondLastLine: false,
                wordWrap: "on",
                padding: { top: 12, bottom: 12 },
              }}
            />
          </div>

          <div className="flex items-center gap-3">
            <label className="block text-sm text-gray-600">
              Upload document (PDF/DOCX/TXT/MD)
            </label>
          </div>
          <div className="flex items-center gap-3">
            <label className="inline-flex items-center px-3 py-2 bg-gray-100 rounded border cursor-pointer hover:bg-gray-200">
              <Upload size={16} className="mr-2" /> Choose File
              <input
                type="file"
                className="hidden"
                accept=".pdf,.docx,.txt,.md"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <span className="text-sm text-gray-600">
              {file ? file.name : "No file selected"}
            </span>
          </div>

          <button
            onClick={extractRules}
            disabled={loading || (!text && !file) || !selectedProjectId}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-60"
          >
            <Wand2 size={16} />
            {loading ? "Extracting…" : "Extract Rule"}
          </button>
        </aside>

        {/* RIGHT PANEL */}
        <main className="flex-1 p-6">
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
            </div>
            <div className="flex items-center gap-2">
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
                  <option value="naming">Naming</option>
                  <option value="performance">Performance</option>
                  <option value="template">Template</option>
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
            {filtered.map((rule, idx) => {
              const isExpanded = expanded.has(idx);
              return (
                <div
                  key={idx}
                  className="border rounded-lg bg-white shadow-sm flex flex-col"
                >
                  <div className="flex items-center justify-between px-4 py-2 border-b bg-gray-50">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-semibold">
                        {rule._id || `Rule ${idx + 1}`}
                      </span>
                      {rule._severity && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700">
                          {rule._severity}
                        </span>
                      )}
                      {rule.category && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">
                          {rule.category}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          rule.status === "approved"
                            ? "bg-green-100 text-green-700"
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
                            if (next.has(idx)) next.delete(idx);
                            else next.add(idx);
                            return next;
                          });
                        }}
                        className="text-xs text-gray-500 hover:text-gray-700"
                      >
                        {isExpanded ? "Collapse" : "Expand"}
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="p-4 space-y-3">
                      <pre className="bg-gray-900 text-gray-100 text-xs rounded p-3 overflow-auto max-h-64">
                        {rule.yaml}
                      </pre>
                      {rule.source_snippet && (
                        <div className="text-xs text-gray-600">
                          <div className="font-semibold mb-1">
                            Source snippet:
                          </div>
                          <pre className="bg-gray-50 border rounded p-2 max-h-32 overflow-auto">
                            {rule.source_snippet}
                          </pre>
                        </div>
                      )}
                      <div className="flex items-center justify-between">
                        <div className="text-xs text-gray-500">
                          Confidence:{" "}
                          <span className="font-semibold">
                            {(rule.confidence * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => openEditor(idx)}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border hover:bg-gray-50"
                          >
                            <Edit3 size={14} />
                            Edit YAML
                          </button>
                          <button
                            onClick={() => approveRule(idx)}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-green-600 text-white hover:bg-green-700"
                          >
                            <Check size={14} />
                            Approve
                          </button>
                          <button
                            onClick={() => discardRule(idx)}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100"
                          >
                            <X size={14} />
                            Discard
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </main>
      </div>

      {/* --- Page Footer --- */}
      <footer className="w-full border-t bg-white p-4 flex justify-end sticky bottom-0 shadow-md">
        <button
          onClick={saveApprovedToPack}
          disabled={!rulePack || results.length === 0}
          className="inline-flex items-center gap-2 px-6 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-60"
        >
          <Save size={16} />
          Save Rules
        </button>
      </footer>

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

      {loading && <LoadingOverlay />}
    </div>
  );
}
