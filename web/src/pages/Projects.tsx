import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { FolderIcon, PlusIcon } from "../components/icons";
import { Layout } from "../components/Layout";
import { EmptyState, IconChip, Modal, PrimaryButton, Spinner, TextInput } from "../components/ui";
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
    <Layout
      title="Projects"
      actions={
        <PrimaryButton onClick={() => setCreating(true)} className="!py-1 text-xs">
          <PlusIcon size={14} />
          New project
        </PrimaryButton>
      }
    >
      {projects.isLoading ? (
        <Spinner label="Loading projects…" />
      ) : (projects.data ?? []).length === 0 ? (
        <EmptyState title="No projects yet">
          Create a project, grab an API key, and point the Python SDK at it to start
          collecting traces.
        </EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.data!.map((project) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className="card group flex flex-col p-5 transition-colors hover:border-accent/40"
            >
              <div className="flex items-center gap-2.5">
                <IconChip>
                  <FolderIcon size={14} />
                </IconChip>
                <h2 className="mono truncate text-[15px] text-ink group-hover:text-accent">
                  {project.name}
                </h2>
              </div>
              <p className="mt-3 line-clamp-2 min-h-10 text-sm text-ink-secondary">
                {project.description ?? "No description"}
              </p>
              <div className="mt-4 flex items-center justify-between border-t border-hairline pt-3">
                <span className="mono text-[11px] text-ink-muted">
                  created {formatTimeAgo(project.created_at)}
                </span>
                <span className="mono text-[11px] text-ink-muted group-hover:text-accent">
                  Open →
                </span>
              </div>
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
