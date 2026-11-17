import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ExperimentStatus } from "../components/ExperimentBits";
import { PlusIcon } from "../components/icons";
import { Layout } from "../components/Layout";
import { EmptyState, GhostButton, Modal, PrimaryButton, Spinner, TextInput } from "../components/ui";
import { api } from "../lib/api";
import { formatScore, formatTimeAgo } from "../lib/format";
import { subscribeLive } from "../lib/sse";

function NewExperimentModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const datasets = useQuery({
    queryKey: ["datasets", projectId],
    queryFn: () => api.listDatasets(projectId),
  });
  const evaluators = useQuery({
    queryKey: ["evaluators", projectId],
    queryFn: () => api.listEvaluators(projectId),
  });
  const [name, setName] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [model, setModel] = useState("claude-opus-5-5");
  const [system, setSystem] = useState("");
  const [prompt, setPrompt] = useState("{{input}}");
  const [picked, setPicked] = useState<string[]>([]);

  useEffect(() => {
    if (datasetId === "" && datasets.data?.[0]) setDatasetId(datasets.data[0].id);
  }, [datasets.data, datasetId]);

  const create = useMutation({
    mutationFn: () =>
      api.createExperiment(projectId, {
        name: name.trim(),
        dataset_id: datasetId,
        target: {
          model: model.trim(),
          system: system.trim() || undefined,
          // Blank prompt: replay each test case's recorded messages unchanged.
          messages: prompt.trim() ? [{ role: "user", content: prompt }] : undefined,
        },
        evaluator_ids: picked,
      }),
    onSuccess: (experiment) => {
      void queryClient.invalidateQueries({ queryKey: ["experiments", projectId] });
      navigate(`/projects/${projectId}/experiments/${experiment.id}`);
    },
  });

  const ready = name.trim() !== "" && datasetId !== "" && model.trim() !== "";
  const area =
    "mono rounded-lg border border-hairline bg-page p-2 text-xs text-ink-secondary focus:border-accent/60 focus:outline-none";

  return (
    <Modal title="New experiment" onClose={onClose} wide>
      {datasets.isLoading ? (
        <Spinner />
      ) : (datasets.data ?? []).length === 0 ? (
        <p className="text-sm text-ink-secondary">
          Create a dataset first — experiments run a model over its test cases.
        </p>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) create.mutate();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs text-ink-muted">
              Name
              <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="prompt-v2" autoFocus />
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-muted">
              Dataset
              <select
                value={datasetId}
                onChange={(event) => setDatasetId(event.target.value)}
                className="mono rounded-lg border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-ink"
              >
                {datasets.data!.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.item_count})
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="flex flex-col gap-1 text-xs text-ink-muted">
            Model
            <TextInput value={model} onChange={(e) => setModel(e.target.value)} className="mono" />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-muted">
            System prompt (optional)
            <textarea rows={2} value={system} onChange={(e) => setSystem(e.target.value)} className={area} />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-muted">
            <span>
              User prompt — <code className="mono">{"{{input}}"}</code> or{" "}
              <code className="mono">{"{{input.field}}"}</code> insert the test case. Leave blank to
              replay recorded messages as-is.
            </span>
            <textarea rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} className={area} />
          </label>
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1 text-xs text-ink-muted">Evaluators</legend>
            {(evaluators.data ?? []).length === 0 ? (
              <p className="text-xs text-ink-muted">None yet — add some on the Evaluators page.</p>
            ) : (
              <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                {evaluators.data!.map((evaluator) => (
                  <label key={evaluator.id} className="mono flex items-center gap-1.5 text-xs text-ink-secondary">
                    <input
                      type="checkbox"
                      checked={picked.includes(evaluator.id)}
                      onChange={(event) =>
                        setPicked((prev) =>
                          event.target.checked
                            ? [...prev, evaluator.id]
                            : prev.filter((id) => id !== evaluator.id),
                        )
                      }
                    />
                    {evaluator.name}
                  </label>
                ))}
              </div>
            )}
          </fieldset>
          <p className="text-[11px] text-ink-muted">
            Without a provider key under Settings, the run uses the built-in simulator.
          </p>
          <div className="flex items-center gap-2">
            <PrimaryButton type="submit" disabled={!ready || create.isPending}>
              {create.isPending ? "Starting…" : "Run experiment"}
            </PrimaryButton>
            {create.isError && (
              <span className="text-xs text-critical">{(create.error as Error).message}</span>
            )}
          </div>
        </form>
      )}
    </Modal>
  );
}

export function ExperimentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  const experiments = useQuery({
    queryKey: ["experiments", projectId],
    queryFn: () => api.listExperiments(projectId!),
    enabled: !!projectId,
  });

  useEffect(() => {
    if (!projectId) return;
    return subscribeLive(projectId, (event) => {
      if (event.type === "experiment.updated") {
        void queryClient.invalidateQueries({ queryKey: ["experiments", projectId] });
      }
    });
  }, [projectId, queryClient]);

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <Layout
      title="Experiments"
      actions={
        <>
          {selected.length >= 2 && (
            <GhostButton
              className="!py-1 text-xs"
              onClick={() =>
                navigate(`/projects/${projectId}/experiments/compare?ids=${selected.join(",")}`)
              }
            >
              Compare {selected.length}
            </GhostButton>
          )}
          <PrimaryButton onClick={() => setCreating(true)} className="!py-1 text-xs">
            <PlusIcon size={14} />
            New experiment
          </PrimaryButton>
        </>
      }
    >
      {experiments.isLoading ? (
        <Spinner label="Loading experiments…" />
      ) : (experiments.data ?? []).length === 0 ? (
        <EmptyState title="No experiments yet">
          An experiment runs a model or your own agent over a dataset and scores every result.
          Start one here, or from code with <code className="mono">tracer.experiment(…)</code>.
        </EmptyState>
      ) : (
        <div className="card">
          <div className="overflow-x-auto rounded-[12px]">
            <table className="mono w-full min-w-[820px] text-[13px]">
              <thead>
                <tr className="border-b border-hairline text-left text-xs text-ink-secondary">
                  <th className="w-10 px-5 py-2.5 font-medium">
                    <span className="sr-only">Select to compare</span>
                  </th>
                  <th className="px-3 py-2.5 font-medium">Experiment</th>
                  <th className="px-3 py-2.5 font-medium">Status</th>
                  <th className="px-3 py-2.5 font-medium">Scores</th>
                  <th className="px-3 py-2.5 text-right font-medium">Cases</th>
                  <th className="px-5 py-2.5 text-right font-medium">Started</th>
                </tr>
              </thead>
              <tbody>
                {experiments.data!.map((experiment) => (
                  <tr key={experiment.id} className="border-b border-hairline last:border-0 hover:bg-surface-2/60">
                    <td className="px-5 py-2.5">
                      <input
                        type="checkbox"
                        aria-label={`Select ${experiment.name} to compare`}
                        checked={selected.includes(experiment.id)}
                        onChange={() => toggle(experiment.id)}
                      />
                    </td>
                    <td className="px-3 py-2.5">
                      <Link
                        to={`/projects/${projectId}/experiments/${experiment.id}`}
                        className="block max-w-[280px] truncate text-ink hover:text-accent"
                      >
                        {experiment.name}
                      </Link>
                      <span className="block text-[10.5px] text-ink-muted">
                        {experiment.target.type === "sdk" ? "SDK run" : experiment.target.model}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <ExperimentStatus experiment={experiment} />
                    </td>
                    <td className="px-3 py-2.5 text-[11px] text-ink-secondary">
                      {Object.entries(experiment.summary?.scores ?? {})
                        .slice(0, 3)
                        .map(([name, score]) => (
                          <span key={name} className="mr-3 whitespace-nowrap">
                            <span className="text-ink-muted">{name}</span>{" "}
                            <span className="tabular-nums">{formatScore(score.mean)}</span>
                          </span>
                        ))}
                    </td>
                    <td className="px-3 py-2.5 text-right text-ink-secondary tabular-nums">
                      {experiment.item_count}
                    </td>
                    <td className="px-5 py-2.5 text-right text-xs text-ink-muted">
                      {formatTimeAgo(experiment.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {creating && projectId && (
        <NewExperimentModal projectId={projectId} onClose={() => setCreating(false)} />
      )}
    </Layout>
  );
}
