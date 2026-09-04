import { useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Layout } from "../components/Layout";
import {
  CopyButton,
  GhostButton,
  Modal,
  PrimaryButton,
  Spinner,
  TextInput,
} from "../components/ui";
import { api } from "../lib/api";
import { formatTimeAgo } from "../lib/format";
import type { ApiKeyCreated } from "../lib/types";

export function SettingsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  if (!projectId) return null;
  return (
    <Layout>
      <h1 className="mb-5 text-lg font-semibold">Settings</h1>
      <div className="flex flex-col gap-6">
        <ApiKeysSection projectId={projectId} />
        <QuickstartSection />
        <CredentialsSection projectId={projectId} />
      </div>
    </Layout>
  );
}

/* ------------------------------------------------------------------ API keys */

function ApiKeysSection({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const keys = useQuery({
    queryKey: ["api-keys", projectId],
    queryFn: () => api.listApiKeys(projectId),
  });
  const [name, setName] = useState("");
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null);

  const create = useMutation({
    mutationFn: () => api.createApiKey(projectId, name || "default"),
    onSuccess: (key) => {
      setCreatedKey(key);
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["api-keys", projectId] });
    },
  });

  const revoke = useMutation({
    mutationFn: (keyId: string) => api.revokeApiKey(projectId, keyId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["api-keys", projectId] }),
  });

  return (
    <section className="card p-5">
      <h2 className="text-sm font-semibold">API keys</h2>
      <p className="mt-1 text-xs text-ink-muted">
        The SDK authenticates ingest with a project API key. Keys are stored hashed — the full
        key is shown only once, at creation.
      </p>

      <form
        className="mt-3 flex gap-2"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <TextInput
          placeholder="Key name (e.g. production)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-64"
        />
        <PrimaryButton type="submit" disabled={create.isPending}>
          Generate key
        </PrimaryButton>
      </form>

      {keys.isLoading ? (
        <div className="mt-4">
          <Spinner />
        </div>
      ) : (
        <ul className="mt-4 flex flex-col gap-2">
          {(keys.data ?? []).map((key) => (
            <li
              key={key.id}
              className="flex flex-wrap items-center gap-2 rounded-md border border-hairline px-3 py-2 text-sm"
            >
              <span className="font-medium">{key.name}</span>
              <span className="mono text-xs text-ink-muted">{key.key_prefix}…</span>
              <span className="text-xs text-ink-muted">
                created {formatTimeAgo(key.created_at)}
                {key.last_used_at && ` · last used ${formatTimeAgo(key.last_used_at)}`}
              </span>
              {key.revoked_at ? (
                <span className="ml-auto text-xs text-critical">revoked</span>
              ) : (
                <GhostButton
                  className="ml-auto !px-2 !py-1 text-xs"
                  onClick={() => revoke.mutate(key.id)}
                >
                  Revoke
                </GhostButton>
              )}
            </li>
          ))}
          {(keys.data ?? []).length === 0 && (
            <p className="text-xs text-ink-muted">No keys yet.</p>
          )}
        </ul>
      )}

      {createdKey && (
        <Modal title="API key created" onClose={() => setCreatedKey(null)}>
          <p className="mb-3 text-xs text-ink-muted">
            Copy this key now — for security it will never be shown again.
          </p>
          <div className="flex items-center gap-2 rounded-md border border-hairline bg-surface-2 px-3 py-2">
            <code className="mono min-w-0 flex-1 break-all text-xs">{createdKey.key}</code>
            <CopyButton text={createdKey.key} />
          </div>
        </Modal>
      )}
    </section>
  );
}

/* ---------------------------------------------------------------- quickstart */

const SNIPPET = `pip install agent-tracer-sdk

# then, in your application:
from agent_tracer import AgentTracer

tracer = AgentTracer(
    api_key="at_…",                      # or AGENT_TRACER_API_KEY env var
    base_url="http://localhost:8000",    # or AGENT_TRACER_BASE_URL
)

with tracer.trace("support-run", session_id="user-42"):
    with tracer.agent("router"):
        with tracer.llm(model="claude-opus-5", messages=msgs) as llm:
            reply = call_model(msgs)          # your existing code
            llm.set_output(reply)
            llm.set_usage(input_tokens=812, output_tokens=310)

        with tracer.tool("search", input={"q": "refund policy"}) as tool:
            tool.set_output(run_search())

# or decorate existing functions:
@tracer.observe(kind="TOOL")
def lookup_order(order_id: str): ...`;

const OTEL_SNIPPET = `# Already using OpenTelemetry / OpenInference instrumentation?
# Point your OTLP HTTP exporter at Agent Tracer instead:
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer at_…"`;

function QuickstartSection() {
  return (
    <section className="card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Instrument your app</h2>
        <CopyButton text={SNIPPET} label="Copy snippet" />
      </div>
      <pre className="mono panel-scroll mt-3 overflow-x-auto rounded-md bg-surface-2 p-4 text-[12px] leading-relaxed text-ink-secondary">
        {SNIPPET}
      </pre>
      <pre className="mono panel-scroll mt-3 overflow-x-auto rounded-md bg-surface-2 p-4 text-[12px] leading-relaxed text-ink-muted">
        {OTEL_SNIPPET}
      </pre>
    </section>
  );
}

/* --------------------------------------------------------------- credentials */

function CredentialsSection({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const credentials = useQuery({
    queryKey: ["credentials", projectId],
    queryFn: () => api.listCredentials(projectId),
  });
  const [provider, setProvider] = useState("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  const save = useMutation({
    mutationFn: () =>
      api.putCredential(projectId, {
        provider,
        api_key: apiKey,
        base_url: baseUrl || null,
      }),
    onSuccess: () => {
      setApiKey("");
      setBaseUrl("");
      void queryClient.invalidateQueries({ queryKey: ["credentials", projectId] });
    },
  });

  const remove = useMutation({
    mutationFn: (p: string) => api.deleteCredential(projectId, p),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["credentials", projectId] }),
  });

  return (
    <section className="card p-5">
      <h2 className="text-sm font-semibold">Replay credentials</h2>
      <p className="mt-1 text-xs text-ink-muted">
        Optional model-provider keys used <em>only</em> to replay LLM spans against the real
        model. Encrypted at rest. Without a key, replays run in the offline simulator.
      </p>

      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Provider
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded-md border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-ink"
          >
            <option value="anthropic">Anthropic</option>
            <option value="openai">OpenAI-compatible</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          API key
          <TextInput
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-…"
            className="w-64"
            required
          />
        </label>
        {provider === "openai" && (
          <label className="flex flex-col gap-1 text-xs text-ink-muted">
            Base URL (optional)
            <TextInput
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com"
              className="w-64"
            />
          </label>
        )}
        <PrimaryButton type="submit" disabled={save.isPending || apiKey.length < 8}>
          Save
        </PrimaryButton>
      </form>

      {credentials.data && credentials.data.length > 0 && (
        <ul className="mt-4 flex flex-col gap-2">
          {credentials.data.map((cred) => (
            <li
              key={cred.provider}
              className="flex items-center gap-3 rounded-md border border-hairline px-3 py-2 text-sm"
            >
              <span className="font-medium capitalize">{cred.provider}</span>
              <span className="mono text-xs text-ink-muted">{cred.masked_key}</span>
              {cred.base_url && (
                <span className="mono text-xs text-ink-muted">{cred.base_url}</span>
              )}
              <GhostButton
                className="ml-auto !px-2 !py-1 text-xs"
                onClick={() => remove.mutate(cred.provider)}
              >
                Remove
              </GhostButton>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
