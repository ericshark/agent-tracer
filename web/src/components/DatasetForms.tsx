import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { fromEditable, toEditable } from "../lib/json";
import { GhostButton, Modal, PrimaryButton, Spinner, TextInput } from "./ui";

const AREA_CLS =
  "mono panel-scroll w-full rounded-lg border border-hairline bg-page p-3 text-xs leading-relaxed text-ink-secondary placeholder:text-ink-muted focus:border-accent/60 focus:outline-none";

export function JsonArea({
  label,
  value,
  onChange,
  rows = 6,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="mono text-[11px] text-ink-muted">{label}</span>
      <textarea
        className={AREA_CLS}
        rows={rows}
        value={value}
        placeholder={placeholder ?? "JSON or plain text"}
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

/** Create or edit a single test case. */
export function ItemEditorModal({
  datasetId,
  item,
  onClose,
}: {
  datasetId: string;
  item?: { id: string; input: unknown; expected_output: unknown };
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [input, setInput] = useState(toEditable(item?.input));
  const [expected, setExpected] = useState(toEditable(item?.expected_output));

  const save = useMutation({
    mutationFn: async () => {
      const payload = { input: fromEditable(input), expected_output: fromEditable(expected) };
      if (item) await api.updateDatasetItem(item.id, payload);
      else await api.createDatasetItems(datasetId, [payload]);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dataset-items", datasetId] });
      void queryClient.invalidateQueries({ queryKey: ["dataset", datasetId] });
      onClose();
    },
  });

  return (
    <Modal title={item ? "Edit test case" : "New test case"} onClose={onClose} wide>
      <form
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <JsonArea label="Input" value={input} onChange={setInput} rows={8} />
        <JsonArea
          label="Expected output (optional)"
          value={expected}
          onChange={setExpected}
          rows={6}
        />
        <div className="flex items-center gap-2">
          <PrimaryButton type="submit" disabled={save.isPending || input.trim() === ""}>
            {save.isPending ? "Saving…" : "Save"}
          </PrimaryButton>
          {save.isError && (
            <span className="text-xs text-critical">{(save.error as Error).message}</span>
          )}
        </div>
      </form>
    </Modal>
  );
}

/** Capture a recorded span (or a trace's root span) as a test case. */
export function AddToDatasetModal({
  projectId,
  tracePk,
  spanPk,
  defaultInput,
  defaultExpected,
  onClose,
}: {
  projectId: string;
  tracePk: string;
  spanPk?: string | null;
  defaultInput: unknown;
  defaultExpected: unknown;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const datasets = useQuery({
    queryKey: ["datasets", projectId],
    queryFn: () => api.listDatasets(projectId),
  });
  const [datasetId, setDatasetId] = useState("");
  const [newName, setNewName] = useState("");
  const [input, setInput] = useState(toEditable(defaultInput));
  const [expected, setExpected] = useState(toEditable(defaultExpected));
  const [savedTo, setSavedTo] = useState<{ id: string; name: string } | null>(null);

  // Default to the first dataset once they load; "new" when there are none.
  useEffect(() => {
    if (datasetId !== "" || !datasets.data) return;
    setDatasetId(datasets.data[0]?.id ?? "new");
  }, [datasets.data, datasetId]);

  const save = useMutation({
    mutationFn: async () => {
      let target = datasets.data?.find((d) => d.id === datasetId);
      if (datasetId === "new") {
        target = await api.createDataset(projectId, { name: newName.trim() });
      }
      if (!target) throw new Error("Pick a dataset");
      // Capture the source link first, then apply any edits made in the form.
      const [created] = await api.addTracesToDataset(target.id, [
        { trace_pk: tracePk, span_pk: spanPk ?? null },
      ]);
      await api.updateDatasetItem(created.id, {
        input: fromEditable(input),
        expected_output: fromEditable(expected),
      });
      return target;
    },
    onSuccess: (target) => {
      void queryClient.invalidateQueries({ queryKey: ["datasets", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["dataset-items", target.id] });
      setSavedTo({ id: target.id, name: target.name });
    },
  });

  const ready =
    input.trim() !== "" && (datasetId === "new" ? newName.trim() !== "" : datasetId !== "");

  return (
    <Modal title="Add to dataset" onClose={onClose} wide>
      {savedTo ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-ink-secondary">
            Saved as a test case in <span className="mono text-ink">{savedTo.name}</span>.
          </p>
          <div className="flex gap-2">
            <Link
              to={`/projects/${projectId}/datasets/${savedTo.id}`}
              className="inline-flex rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-ink hover:bg-accent-strong"
            >
              Open dataset
            </Link>
            <GhostButton onClick={onClose}>Done</GhostButton>
          </div>
        </div>
      ) : datasets.isLoading ? (
        <Spinner />
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) save.mutate();
          }}
        >
          <p className="text-xs text-ink-muted">
            Turn this recorded step into a test case. Edit the expected output to what the
            agent <em>should</em> have produced, then run experiments against it.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs text-ink-muted">
              Dataset
              <select
                value={datasetId}
                onChange={(event) => setDatasetId(event.target.value)}
                className="mono rounded-lg border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-ink"
              >
                {(datasets.data ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.item_count})
                  </option>
                ))}
                <option value="new">+ New dataset…</option>
              </select>
            </label>
            {datasetId === "new" && (
              <TextInput
                aria-label="New dataset name"
                placeholder="Dataset name"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                className="mono flex-1"
                autoFocus
              />
            )}
          </div>
          <JsonArea label="Input" value={input} onChange={setInput} rows={7} />
          <JsonArea label="Expected output" value={expected} onChange={setExpected} rows={6} />
          <div className="flex items-center gap-2">
            <PrimaryButton type="submit" disabled={!ready || save.isPending}>
              {save.isPending ? "Saving…" : "Add test case"}
            </PrimaryButton>
            {save.isError && (
              <span className="text-xs text-critical">{(save.error as Error).message}</span>
            )}
          </div>
        </form>
      )}
    </Modal>
  );
}
