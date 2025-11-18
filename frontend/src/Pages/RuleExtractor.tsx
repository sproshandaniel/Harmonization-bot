import { useMemo, useState } from "react";
import { Upload, FileText, Wand2, Filter, Check, X, Edit3, Save } from "lucide-react";
import Modal from "../Components/modal";
import Editor from "@monaco-editor/react";
import yaml from "js-yaml";

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

export default function RuleExtractor() {
  // Core states
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<RuleResult[]>([]);
  const [pack, setPack] = useState<string>("abap-core-standards");
  const [filter, setFilter] = useState<{ category?: string; q?: string }>({});

  // Editor modal
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorIdx, setEditorIdx] = useState<number | null>(null);
  const [editorValue, setEditorValue] = useState<string>("");
  const [editorError, setEditorError] = useState<string | null>(null);

  // Expanded rule card state (fix for hooks warning)
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const filtered = useMemo(() => {
    return results.filter((r) => {
      const matchesCat = filter.category ? r.category === filter.category : true;
      const matchesQuery = filter.q ? r.yaml.toLowerCase().includes(filter.q.toLowerCase()) : true;
      return matchesCat && matchesQuery && r.status !== "discarded";
    });
  }, [results, filter]);

  // ---- API call ----
  async function extractRules() {
    setLoading(true);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      else form.append("text", text);

      const res = await fetch(file ? "/api/extract-from-document" : "/api/extract-rule", {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(`Backend responded with ${res.status}`);
      const data = await res.json();
      const rules: RuleResult[] = (data.rules ? data.rules : [data]).map(tagDerived);
      setResults(rules.map((r) => ({ status: "new", ...r })));
    } catch (e) {
      console.error(e);
      alert("Extraction failed. Check backend logs.");
    } finally {
      setLoading(false);
    }
  }

  // ---- Actions ----
  function approveRule(idx: number) {
    setResults((prev) => prev.map((r, i) => (i === idx ? { ...r, status: "approved" } : r)));
  }
  function discardRule(idx: number) {
    setResults((prev) => prev.map((r, i) => (i === idx ? { ...r, status: "discarded" } : r)));
  }

  // ---- YAML editor ----
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
      prev.map((r, i) => (i === editorIdx ? tagDerived({ ...r, yaml: editorValue, status: "edited" }) : r))
    );
    setEditorOpen(false);
  }

  // ---- Save approved to pack ----
  async function saveApprovedToPack() {
    const approved = results.filter((r) => r.status === "approved" || r.status === "edited");
    if (!approved.length) return alert("No approved rules to save.");
    try {
      const res = await fetch(`/api/packs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: pack,
          status: "draft",
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

  // ---- Helper ----
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

  return (
    <div className="flex min-h-[calc(100vh-64px)] bg-gray-50">
      {/* LEFT PANEL */}
      <aside className="w-full lg:w-[36%] border-r bg-white p-6 space-y-4">
        <div className="flex items-center gap-2 text-indigo-700 font-semibold">
          <Wand2 size={18} />
          <span>Rule Extraction</span>
        </div>

        <div className="flex items-center justify-between">
          <label className="block text-sm text-gray-600">Paste code or guideline text</label>
        </div>

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

        {/* Upload */}
        <div className="flex items-center gap-3">
          <label className="block text-sm text-gray-600">Upload document (PDF/DOCX/TXT/MD)</label>
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
          <span className="text-sm text-gray-600">{file ? file.name : "No file selected"}</span>
        </div>

        {/* Extract Button */}
        <button
          onClick={extractRules}
          disabled={loading || (!text && !file)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-60"
        >
          <Wand2 size={16} />
          {loading ? "Extracting…" : "Extract Rule"}
        </button>

        {/* Save Pack */}
        <div className="pt-6 border-t">
          <label className="block text-sm text-gray-600 mb-2">Save approved rules to pack</label>
          <div className="flex gap-3">
            <input
              className="border rounded px-3 py-2 flex-1"
              value={pack}
              onChange={(e) => setPack(e.target.value)}
              placeholder="abap-core-standards"
            />
            <button
              onClick={saveApprovedToPack}
              className="inline-flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
            >
              <Save size={16} /> Save
            </button>
          </div>
        </div>
      </aside>

      {/* RIGHT PANEL */}
      <main className="flex-1 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2 text-gray-700">
            <FileText size={18} />
            <span className="font-semibold">Extracted Rules</span>
            <span className="text-sm text-gray-500">
              ({results.filter((r) => r.status !== "discarded").length})
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 border rounded px-2 py-1 bg-white">
              <Filter size={16} />
              <select
                className="text-sm outline-none"
                value={filter.category || ""}
                onChange={(e) => setFilter((f) => ({ ...f, category: e.target.value || undefined }))}
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
              onChange={(e) => setFilter((f) => ({ ...f, q: e.target.value }))}
            />
          </div>
        </div>

        {/* Rule Cards */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {filtered.map((r, idx) => {
            const isExpanded = expanded.has(idx);
            const toggleExpanded = () => {
              const next = new Set(expanded);
              isExpanded ? next.delete(idx) : next.add(idx);
              setExpanded(next);
            };

            const severityColor =
              r._severity === "error"
                ? "bg-red-100 text-red-700 border border-red-200"
                : r._severity === "warn"
                ? "bg-yellow-100 text-yellow-800 border border-yellow-200"
                : "bg-green-100 text-green-700 border border-green-200";

            return (
              <div key={idx} className="bg-white rounded-lg shadow-sm border hover:shadow-md transition overflow-hidden">
                {/* Header */}
                <div className="px-4 py-3 flex flex-wrap justify-between items-center border-b bg-gray-50">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-indigo-700 text-sm">
                      {r._id ?? `Rule #${idx + 1}`}
                    </span>
                    {r._severity && (
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${severityColor}`}>
                        {r._severity}
                      </span>
                    )}
                    {r.category && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                        {r.category}
                      </span>
                    )}
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200">
                      Confidence {Math.round((r.confidence ?? 0) * 100)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <button onClick={() => approveRule(idx)} className="text-green-700 text-xs font-medium">
                      ✅ Approve
                    </button>
                    <button onClick={() => openEditor(idx)} className="text-indigo-700 text-xs font-medium">
                      ✏️ Edit
                    </button>
                    <button onClick={() => discardRule(idx)} className="text-red-600 text-xs font-medium">
                      🗑 Discard
                    </button>
                  </div>
                </div>

                {/* Summary */}
                <div className="px-4 py-3 text-sm text-gray-700">
                  <p className="mb-2">
                    <span className="font-semibold">Title:</span>{" "}
                    {r.yaml.match(/title:\s*(.*)/)?.[1]?.replace(/['"]/g, "") ?? "—"}
                  </p>
                  <p className="mb-2">
                    <span className="font-semibold">Description:</span>{" "}
                    {r.yaml.match(/description:\s*(.*)/)?.[1]?.replace(/['"]/g, "") ?? "—"}
                  </p>
                  <button
                    onClick={toggleExpanded}
                    className="text-indigo-600 text-xs font-medium hover:underline"
                  >
                    {isExpanded ? "Hide Details ▲" : "Show Full Rule ▼"}
                  </button>
                </div>

                {/* Collapsible YAML */}
                {isExpanded && (
                  <pre className="p-4 bg-gray-50 text-sm overflow-x-auto border-t whitespace-pre-wrap">
                    {r.yaml}
                  </pre>
                )}

                {r.source_snippet && (
                  <div className="px-4 py-3 bg-white border-t text-xs text-gray-600">
                    <div className="font-semibold mb-1">Source snippet</div>
                    <pre className="bg-gray-50 p-3 rounded text-xs overflow-x-auto">
                      {r.source_snippet}
                    </pre>
                  </div>
                )}

                <div className="px-4 py-2 bg-gray-50 text-xs text-gray-600 border-t">
                  Status: <span className="font-medium">{r.status ?? "new"}</span>
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && (
            <div className="text-sm text-gray-500">No rules extracted yet.</div>
          )}
        </div>
      </main>

      {/* YAML Editor Modal */}
      <Modal
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        title="Edit Rule YAML"
        footer={
          <div className="flex items-center justify-between">
            <div className={`text-xs ${editorError ? "text-red-600" : "text-green-700"}`}>
              {editorError ? `YAML error: ${editorError}` : "Valid YAML"}
            </div>
            <div className="flex gap-2">
              <button onClick={() => setEditorOpen(false)} className="px-3 py-1.5 rounded border">
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
    </div>
  );
}
