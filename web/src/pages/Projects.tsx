import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Layout } from "../components/Layout";
import { EmptyState, Modal, PrimaryButton, Spinner, TextInput } from "../components/ui";
import { api } from "../lib/api";
import { formatTimeAgo } from "../lib/format";

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.listProjects });
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const create = useMutation({
    mutationFn: () => api.createProject({ name, description: description || undefined }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      setCreating(false);
      setName("");
      setDescription("");
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };

  return (
    <Layout>
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Projects</h1>
        <PrimaryButton onClick={() => setCreating(true)}>+ New project</PrimaryButton>
      </div>

      {projects.isLoading ? (
        <Spinner label="Loading projects…" />
      ) : (projects.data ?? []).length === 0 ? (
        <EmptyState title="No projects yet">
          Create a project, grab an API key, and point the Python SDK at it to start
          collecting traces.
        </EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.data!.map((project) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className="card group p-4 transition-colors hover:border-accent/50"
            >
              <h2 className="font-medium group-hover:text-accent">{project.name}</h2>
              <p className="mt-1 line-clamp-2 min-h-8 text-sm text-ink-muted">
                {project.description ?? "No description"}
              </p>
              <p className="mt-3 text-xs text-ink-muted">
                created {formatTimeAgo(project.created_at)}
              </p>
            </Link>
          ))}
        </div>
      )}

      {creating && (
        <Modal title="New project" onClose={() => setCreating(false)}>
          <form onSubmit={submit} className="flex flex-col gap-3">
            <TextInput
              placeholder="Project name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
            <TextInput
              placeholder="Description (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <PrimaryButton type="submit" disabled={create.isPending || !name.trim()}>
              Create project
            </PrimaryButton>
          </form>
        </Modal>
      )}
    </Layout>
  );
}
