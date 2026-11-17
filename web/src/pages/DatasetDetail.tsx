import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ItemEditorModal, JsonArea } from "../components/DatasetForms";
import { PlusIcon } from "../components/icons";
import { Layout } from "../components/Layout";
import { EmptyState, GhostButton, Modal, PrimaryButton, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { formatTimeAgo } from "../lib/format";
import { preview } from "../lib/json";
import type { DatasetItem } from "../lib/types";

const PAGE_SIZE = 50;

function ImportModal({ datasetId, onClose }: { datasetId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [format, setFormat] = useState<"jsonl" | "csv">("jsonl");
  const [content, setContent] = useState("");

  const run = useMutation({
    mutationFn: () => api.importDataset(datasetId, format, content),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dataset-items", datasetId] });
      void queryClient.invalidateQueries({ queryKey: ["dataset", datasetId] });
      onClose();
    },
  });

  return (
    <Modal title="Import test cases" onClose={onClose} wide>
      <div className="flex flex-col gap-3">
        <p className="text-xs text-ink-muted">
          JSONL: one object per line with <code className="mono">input</code> and optional{" "}
          <code className="mono">expected_output</code> / <code className="mono">metadata</code>.
          CSV: a header row; without an <code className="mono">input</code> column, the other
          columns become the input.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Format"
            value={format}
            onChange={(event) => setFormat(event.target.value as "jsonl" | "csv")}
            className="mono rounded-lg border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-ink"
          >
            <option value="jsonl">JSONL</option>
            <option value="csv">CSV</option>
          </select>
          <input
            type="file"
            accept=".jsonl,.ndjson,.json,.csv,text/csv"
            aria-label="Choose a file"
            className="text-xs text-ink-muted file:mr-2 file:rounded-lg file:border file:border-hairline file:bg-surface-2 file:px-2.5 file:py-1 file:text-ink"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              if (file.name.toLowerCase().endsWith(".csv")) setFormat("csv");
              setContent(await file.text());
            }}
          />
        </div>
        <JsonArea
          label="…or paste content"
          value={content}
          onChange={setContent}
          rows={10}
          placeholder={'{"input": {"question": "…"}, "expected_output": "…"}'}
        />
        <div className="flex items-center gap-2">
          <PrimaryButton
            onClick={() => run.mutate()}
            disabled={run.isPending || content.trim() === ""}
          >
            {run.isPending ? "Importing…" : "Import"}
          </PrimaryButton>
          {run.isError && (
            <span className="text-xs text-critical">{(run.error as Error).message}</span>
          )}
        </div>
      </div>
    </Modal>
  );
}

export function DatasetDetailPage() {
  const { projectId, datasetId } = useParams<{ projectId: string; datasetId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState<DatasetItem | "new" | null>(null);
  const [importing, setImporting] = useState(false);

  const dataset = useQuery({
    queryKey: ["dataset", datasetId],
    queryFn: () => api.getDataset(datasetId!),
    enabled: !!datasetId,
  });
  const items = useQuery({
    queryKey: ["dataset-items", datasetId, page],
    queryFn: () =>
      api.listDatasetItems(datasetId!, { limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    enabled: !!datasetId,
    placeholderData: (previous) => previous,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["dataset-items", datasetId] });
    void queryClient.invalidateQueries({ queryKey: ["dataset", datasetId] });
  };
  const removeItem = useMutation({
    mutationFn: (itemId: string) => api.deleteDatasetItem(itemId),
    onSuccess: refresh,
  });
  const removeDataset = useMutation({
    mutationFn: () => api.deleteDataset(datasetId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["datasets", projectId] });
      navigate(`/projects/${projectId}/datasets`);
    },
  });

  const download = async () => {
    const text = await api.exportDataset(datasetId!);
    const url = URL.createObjectURL(new Blob([text], { type: "application/x-ndjson" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${dataset.data?.name ?? "dataset"}.jsonl`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (dataset.isLoading || !dataset.data) {
    return (
      <Layout title="Dataset">
        {dataset.isError ? (
          <EmptyState title="Dataset not found" />
        ) : (
          <Spinner label="Loading dataset…" />
        )}
      </Layout>
    );
  }

  const total = items.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Layout
      title="Dataset"
      actions={
        <PrimaryButton onClick={() => setEditing("new")} className="!py-1 text-xs">
          <PlusIcon size={14} />
          Add case
        </PrimaryButton>
      }
    >
      <nav className="mono mb-3 text-[11px] text-ink-muted">
        <Link to={`/projects/${projectId}/datasets`} className="hover:text-ink-secondary">
          Datasets
        </Link>
        <span className="mx-1.5">/</span>
        <span>{dataset.data.name}</span>
      </nav>

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="mono text-xl text-ink">{dataset.data.name}</h2>
          <p className="mt-1 text-sm text-ink-muted">
            {dataset.data.description ?? "No description"} · {dataset.data.item_count} test case
            {dataset.data.item_count === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <GhostButton onClick={() => setImporting(true)} className="!py-1 text-xs">
            Import
          </GhostButton>
          <GhostButton onClick={() => void download()} className="!py-1 text-xs" disabled={total === 0}>
            Export JSONL
          </GhostButton>
          <GhostButton
            className="!py-1 text-xs hover:!text-critical"
            disabled={removeDataset.isPending}
            onClick={() => {
              if (window.confirm(`Delete dataset "${dataset.data.name}" and all its test cases?`)) {
                removeDataset.mutate();
              }
            }}
          >
            Delete
          </GhostButton>
        </div>
      </div>

      {items.isLoading ? (
        <Spinner label="Loading test cases…" />
      ) : total === 0 ? (
        <EmptyState title="No test cases yet">
          Add one by hand, import a JSONL or CSV file, or open a trace and choose{" "}
          <em>Add to dataset</em> on a span.
        </EmptyState>
      ) : (
        <div className="card">
          <div className="overflow-x-auto rounded-[12px]">
            <table className="mono w-full min-w-[760px] table-fixed text-[12px]">
              <thead>
                <tr className="border-b border-hairline text-left text-xs text-ink-secondary">
                  <th className="w-[42%] px-5 py-2.5 font-medium">Input</th>
                  <th className="w-[34%] px-3 py-2.5 font-medium">Expected output</th>
                  <th className="px-3 py-2.5 font-medium">Source</th>
                  <th className="w-24 px-5 py-2.5 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.data!.items.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-hairline align-top last:border-0 hover:bg-surface-2/60"
                  >
                    <td className="px-5 py-2.5 break-words text-ink-secondary">
                      {preview(item.input)}
                    </td>
                    <td className="px-3 py-2.5 break-words text-ink-secondary">
                      {preview(item.expected_output)}
                    </td>
                    <td className="px-3 py-2.5 text-[11px] text-ink-muted">
                      {item.source_trace_pk ? (
                        <Link
                          to={`/projects/${projectId}/traces/${item.source_trace_pk}`}
                          className="text-ink-secondary hover:text-accent"
                        >
                          from trace
                        </Link>
                      ) : (
                        "manual"
                      )}
                      <span className="block">{formatTimeAgo(item.created_at)}</span>
                    </td>
                    <td className="px-5 py-2.5 text-right">
                      <button
                        type="button"
                        className="text-ink-muted hover:text-ink"
                        onClick={() => setEditing(item)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        aria-label="Delete test case"
                        className="ml-3 text-ink-muted hover:text-critical"
                        onClick={() => removeItem.mutate(item.id)}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pageCount > 1 && (
            <div className="mono flex items-center justify-between border-t border-hairline px-5 py-2.5 text-[11px] text-ink-muted">
              <span>
                Page {page + 1} of {pageCount}
              </span>
              <span className="flex gap-2">
                <GhostButton
                  className="!px-2 !py-0.5 text-[11px]"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </GhostButton>
                <GhostButton
                  className="!px-2 !py-0.5 text-[11px]"
                  disabled={page + 1 >= pageCount}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </GhostButton>
              </span>
            </div>
          )}
        </div>
      )}

      {editing && datasetId && (
        <ItemEditorModal
          datasetId={datasetId}
          item={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
      {importing && datasetId && (
        <ImportModal datasetId={datasetId} onClose={() => setImporting(false)} />
      )}
    </Layout>
  );
}
