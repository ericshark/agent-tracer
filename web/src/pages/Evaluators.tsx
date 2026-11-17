import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PlusIcon } from "../components/icons";
import { Layout } from "../components/Layout";
import { EmptyState, Modal, PrimaryButton, Spinner, TextInput } from "../components/ui";
import { api } from "../lib/api";
import type { EvaluatorTemplate, TemplateParam } from "../lib/types";

const KIND_LABEL: Record<EvaluatorTemplate["kind"], string> = {
  code: "Deterministic",
  trajectory: "Trajectory",
  llm_judge: "LLM judge",
};

/** Text-field value → the typed value the API expects. Blank means "not set". */
function parseParam(param: TemplateParam, raw: string): unknown {
  const text = raw.trim();
  if (text === "") return undefined;
  if (param.type === "number") return Number(text);
  if (param.type === "string_list") {
    return text
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }
  if (param.type === "json") return JSON.parse(text);
  return raw;
}

function CreateModal({
  projectId,
  templates,
  onClose,
}: {
  projectId: string;
  templates: EvaluatorTemplate[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [templateKey, setTemplateKey] = useState(templates[0]?.key ?? "");
  const [name, setName] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [flags, setFlags] = useState<Record<string, boolean>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const template = templates.find((t) => t.key === templateKey);

  const create = useMutation({
    mutationFn: (config: Record<string, unknown>) =>
      api.createEvaluator(projectId, {
        name: name.trim() || templateKey,
        template: templateKey,
        config,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["evaluators", projectId] });
      onClose();
    },
  });

  const submit = () => {
    if (!template) return;
    const config: Record<string, unknown> = {};
    try {
      for (const param of template.params) {
        if (param.type === "boolean") {
          if (param.name in flags) config[param.name] = flags[param.name];
          continue;
        }
        const parsed = parseParam(param, values[param.name] ?? "");
        if (parsed !== undefined) config[param.name] = parsed;
      }
    } catch {
      setFormError("One of the JSON fields is not valid JSON.");
      return;
    }
    setFormError(null);
    create.mutate(config);
  };

  return (
    <Modal title="New evaluator" onClose={onClose} wide>
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Type
          <select
            value={templateKey}
            onChange={(event) => {
              setTemplateKey(event.target.value);
              setValues({});
              setFlags({});
            }}
            className="mono rounded-lg border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-ink"
          >
            {(["code", "trajectory", "llm_judge"] as const).map((kind) => (
              <optgroup key={kind} label={KIND_LABEL[kind]}>
                {templates
                  .filter((t) => t.kind === kind)
                  .map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.title}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        </label>
        {template && (
          <p className="text-xs text-ink-secondary">
            {template.description}
            {template.needs_expected && " Needs an expected output."}
            {template.needs_trace && " Needs a recorded trace."}
          </p>
        )}
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Score name
          <TextInput
            placeholder={templateKey}
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="mono"
          />
        </label>
        {template?.params.map((param) =>
          param.type === "boolean" ? (
            <label key={param.name} className="flex items-center gap-2 text-xs text-ink-secondary">
              <input
                type="checkbox"
                checked={flags[param.name] ?? Boolean(param.default)}
                onChange={(event) =>
                  setFlags((prev) => ({ ...prev, [param.name]: event.target.checked }))
                }
              />
              {param.description}
            </label>
          ) : (
            <label key={param.name} className="flex flex-col gap-1 text-xs text-ink-muted">
              <span>
                <span className="mono text-ink-secondary">{param.name}</span>
                {param.required && <span className="text-critical"> *</span>} — {param.description}
              </span>
              {param.type === "select" ? (
                <select
                  value={values[param.name] ?? String(param.default ?? "")}
                  onChange={(event) =>
                    setValues((prev) => ({ ...prev, [param.name]: event.target.value }))
                  }
                  className="mono rounded-lg border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-ink"
                >
                  {param.options.map((option) => (
                    <option key={option}>{option}</option>
                  ))}
                </select>
              ) : param.type === "json" || param.name === "rubric" ? (
                <textarea
                  rows={4}
                  spellCheck={false}
                  value={values[param.name] ?? ""}
                  onChange={(event) =>
                    setValues((prev) => ({ ...prev, [param.name]: event.target.value }))
                  }
                  className="mono rounded-lg border border-hairline bg-page p-2 text-xs text-ink-secondary focus:border-accent/60 focus:outline-none"
                />
              ) : (
                <TextInput
                  value={values[param.name] ?? ""}
                  placeholder={
                    param.type === "string_list"
                      ? "comma, separated"
                      : param.default != null
                        ? String(param.default)
                        : ""
                  }
                  onChange={(event) =>
                    setValues((prev) => ({ ...prev, [param.name]: event.target.value }))
                  }
                  className="mono"
                />
              )}
            </label>
          ),
        )}
        <div className="flex items-center gap-2">
          <PrimaryButton onClick={submit} disabled={create.isPending || !template}>
            {create.isPending ? "Saving…" : "Create evaluator"}
          </PrimaryButton>
          {(formError || create.isError) && (
            <span className="text-xs text-critical">
              {formError ?? (create.error as Error).message}
            </span>
          )}
        </div>
      </div>
    </Modal>
  );
}

export function EvaluatorsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);

  const templates = useQuery({ queryKey: ["evaluator-templates"], queryFn: api.listTemplates });
  const evaluators = useQuery({
    queryKey: ["evaluators", projectId],
    queryFn: () => api.listEvaluators(projectId!),
    enabled: !!projectId,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteEvaluator(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["evaluators", projectId] }),
  });
  const byKey = useMemo(
    () => new Map((templates.data ?? []).map((t) => [t.key, t])),
    [templates.data],
  );

  return (
    <Layout
      title="Evaluators"
      actions={
        <PrimaryButton
          onClick={() => setCreating(true)}
          className="!py-1 text-xs"
          disabled={!templates.data}
        >
          <PlusIcon size={14} />
          New evaluator
        </PrimaryButton>
      }
    >
      {evaluators.isLoading ? (
        <Spinner label="Loading evaluators…" />
      ) : (evaluators.data ?? []).length === 0 ? (
        <EmptyState title="No evaluators yet">
          An evaluator turns a run into a score. Pick a deterministic check (exact match, JSON
          schema, budgets), a trajectory check (did the agent call the right tools?), or an LLM
          judge with a rubric — then use it in experiments or run it on any trace.
        </EmptyState>
      ) : (
        <div className="card">
          <ul>
            {evaluators.data!.map((evaluator) => {
              const template = byKey.get(evaluator.template);
              return (
                <li
                  key={evaluator.id}
                  className="flex flex-wrap items-center gap-3 border-b border-hairline px-5 py-3 last:border-0"
                >
                  <div className="min-w-0 flex-1">
                    <p className="mono truncate text-[13px] text-ink">{evaluator.name}</p>
                    <p className="mt-0.5 truncate text-xs text-ink-muted">
                      {template?.title ?? evaluator.template}
                      {Object.keys(evaluator.config).length > 0 && (
                        <span className="mono"> · {JSON.stringify(evaluator.config)}</span>
                      )}
                    </p>
                  </div>
                  {template && (
                    <span className="mono rounded-md border border-hairline bg-surface-2 px-1.5 py-0.5 text-[10.5px] text-ink-secondary">
                      {KIND_LABEL[template.kind]}
                    </span>
                  )}
                  <button
                    type="button"
                    aria-label={`Delete evaluator ${evaluator.name}`}
                    className="text-ink-muted hover:text-critical"
                    onClick={() => remove.mutate(evaluator.id)}
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {creating && projectId && templates.data && (
        <CreateModal
          projectId={projectId}
          templates={templates.data}
          onClose={() => setCreating(false)}
        />
      )}
    </Layout>
  );
}
