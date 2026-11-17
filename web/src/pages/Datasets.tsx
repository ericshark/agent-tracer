import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DatabaseIcon, PlusIcon } from "../components/icons";
import { Layout } from "../components/Layout";
import { EmptyState, IconChip, Modal, PrimaryButton, Spinner, TextInput } from "../components/ui";
import { api } from "../lib/api";
import { formatCount, formatTimeAgo } from "../lib/format";

export function DatasetsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const datasets = useQuery({
    queryKey: ["datasets", projectId],
    queryFn: () => api.listDatasets(projectId!),
    enabled: !!projectId,
  });

  const create = useMutation({
    mutationFn: () =>
      api.createDataset(projectId!, {
        name: name.trim(),
        description: description.trim() || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["datasets", projectId] });
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
      title="Datasets"
      actions={
        <PrimaryButton onClick={() => setCreating(true)} className="!py-1 text-xs">
          <PlusIcon size={14} />
          New dataset
        </PrimaryButton>
      }
    >
      {datasets.isLoading ? (
        <Spinner label="Loading datasets…" />
      ) : (datasets.data ?? []).length === 0 ? (
        <EmptyState title="No datasets yet">
          A dataset is a set of test cases — an input and the output you expect. Create one
          here, import a file, or open any trace and choose <em>Add to dataset</em> to turn a
          real run into a regression test.
        </EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {datasets.data!.map((dataset) => (
            <Link
              key={dataset.id}
              to={`/projects/${projectId}/datasets/${dataset.id}`}
              className="card group flex flex-col p-5 transition-colors hover:border-accent/40"
            >
              <div className="flex items-center gap-2.5">
                <IconChip>
                  <DatabaseIcon size={14} />
                </IconChip>
                <h2 className="mono truncate text-[15px] text-ink group-hover:text-accent">
                  {dataset.name}
                </h2>
              </div>
              <p className="mt-3 line-clamp-2 min-h-10 text-sm text-ink-secondary">
                {dataset.description ?? "No description"}
              </p>
              <div className="mt-4 flex items-center justify-between border-t border-hairline pt-3">
                <span className="mono text-[11px] text-ink-muted tabular-nums">
                  {formatCount(dataset.item_count)} test case
                  {dataset.item_count === 1 ? "" : "s"}
                </span>
                <span className="mono text-[11px] text-ink-muted">
                  created {formatTimeAgo(dataset.created_at)}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {creating && (
        <Modal title="New dataset" onClose={() => setCreating(false)}>
          <form onSubmit={submit} className="flex flex-col gap-3">
            <TextInput
              placeholder="Dataset name"
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
              Create dataset
            </PrimaryButton>
            {create.isError && (
              <p className="text-xs text-critical">{(create.error as Error).message}</p>
            )}
          </form>
        </Modal>
      )}
    </Layout>
  );
}
