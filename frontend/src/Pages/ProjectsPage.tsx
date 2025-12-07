import React, { useEffect, useState } from "react";

type ProjectRole = "architect" | "senior_developer" | "developer";

type ProjectMember = {
  name: string;
  email: string;
  role: ProjectRole;
};

type Project = {
  id?: string;
  name: string;
  description?: string;
  members: ProjectMember[];
};

const emptyMember: ProjectMember = {
  name: "",
  email: "",
  role: "developer",
};

const ProjectsPage: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [members, setMembers] = useState<ProjectMember[]>([emptyMember]);

  // Load existing projects (for list sidebar)
  useEffect(() => {
    const fetchProjects = async () => {
      try {
        setLoading(true);
        const res = await fetch("/api/projects");
        if (!res.ok) throw new Error(`Failed to load projects (${res.status})`);
        const data = await res.json();
        setProjects(Array.isArray(data) ? data : data.projects || []);
      } catch (err: any) {
        console.error(err);
        setError(err.message || "Error loading projects");
      } finally {
        setLoading(false);
      }
    };
    fetchProjects();
  }, []);

  const addMemberRow = () => {
    setMembers((prev) => [...prev, { ...emptyMember }]);
  };

  const updateMember = (index: number, field: keyof ProjectMember, value: string) => {
    setMembers((prev) =>
      prev.map((m, i) =>
        i === index ? { ...m, [field]: field === "role" ? value as ProjectRole : value } : m
      )
    );
  };

  const removeMember = (index: number) => {
    setMembers((prev) => prev.filter((_, i) => i !== index));
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      alert("Project name is required.");
      return;
    }

    const cleanMembers = members.filter(
      (m) => m.name.trim() && m.email.trim()
    );

    if (!cleanMembers.length) {
      alert("Please add at least one member (architect/senior developer/developer).");
      return;
    }

    try {
      setSaving(true);
      setError(null);
      const payload: Project = {
        name: name.trim(),
        description: description.trim() || undefined,
        members: cleanMembers,
      };

      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Failed to create project (${res.status})`);
      }

      const created = await res.json();

      setProjects((prev) => [...prev, created]);
      setName("");
      setDescription("");
      setMembers([emptyMember]);
      alert("Project created successfully.");
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Error creating project");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-full bg-gray-50">
      {/* Left: existing projects list */}
      <aside className="w-72 border-r bg-white p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Existing Projects
        </h2>
        {loading && <p className="text-xs text-gray-500">Loading projects…</p>}
        {error && (
          <p className="text-xs text-red-600 mb-2">
            {error}
          </p>
        )}
        <ul className="space-y-1 text-sm">
          {projects.map((p) => (
            <li
              key={p.id || p.name}
              className="px-2 py-1 rounded hover:bg-gray-100 cursor-default"
            >
              <div className="font-medium">{p.name}</div>
              {p.description && (
                <div className="text-xs text-gray-500 line-clamp-2">
                  {p.description}
                </div>
              )}
            </li>
          ))}
          {!loading && projects.length === 0 && (
            <li className="text-xs text-gray-400">
              No projects yet. Create one on the right.
            </li>
          )}
        </ul>
      </aside>

      {/* Right: create/edit project form */}
      <main className="flex-1 p-6">
        <h1 className="text-lg font-semibold text-gray-800 mb-4">
          Create Project
        </h1>
        <p className="text-sm text-gray-600 mb-6">
          A project groups rules, documents and conversations. Assign{" "}
          <strong>Architects</strong>, <strong>Senior Developers</strong> and{" "}
          <strong>Developers</strong>; their roles will control how the bot
          and approval flows work.
        </p>

        <form
          onSubmit={handleCreateProject}
          className="space-y-6 max-w-3xl bg-white border rounded-lg p-5 shadow-sm"
        >
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Project Name <span className="text-red-500">*</span>
            </label>
            <input
              className="border rounded w-full px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. ABAP Core Harmonization"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              className="border rounded w-full px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the scope of this project (systems, modules, teams, etc.)"
            />
          </div>

          {/* Members */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">
                Team Members & Roles
              </label>
              <button
                type="button"
                onClick={addMemberRow}
                className="text-xs px-3 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700"
              >
                + Add Member
              </button>
            </div>
            <p className="text-xs text-gray-500 mb-3">
              Add at least one Architect. Roles determine who can approve rules,
              override decisions and interact with the bot in advanced modes.
            </p>

            <div className="space-y-3">
              {members.map((m, idx) => (
                <div
                  key={idx}
                  className="grid grid-cols-1 md:grid-cols-12 gap-2 items-center"
                >
                  <input
                    className="md:col-span-4 border rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500"
                    placeholder="Full name"
                    value={m.name}
                    onChange={(e) => updateMember(idx, "name", e.target.value)}
                  />
                  <input
                    className="md:col-span-5 border rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500"
                    placeholder="Email"
                    type="email"
                    value={m.email}
                    onChange={(e) => updateMember(idx, "email", e.target.value)}
                  />
                  <select
                    className="md:col-span-2 border rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500"
                    value={m.role}
                    onChange={(e) => updateMember(idx, "role", e.target.value)}
                  >
                    <option value="architect">Architect</option>
                    <option value="senior_developer">Senior Developer</option>
                    <option value="developer">Developer</option>
                  </select>
                  <div className="md:col-span-1 flex justify-end">
                    {members.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeMember(idx)}
                        className="text-xs text-red-500 hover:text-red-700"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={() => {
                setName("");
                setDescription("");
                setMembers([emptyMember]);
              }}
              className="px-4 py-2 text-sm border rounded hover:bg-gray-50"
            >
              Reset
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {saving ? "Saving…" : "Create Project"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
};

export default ProjectsPage;
