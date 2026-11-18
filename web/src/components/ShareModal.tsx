import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { SharedMetrics } from "../pages/SharePage";
import { api } from "../lib/api";
import { formatTimeAgo } from "../lib/format";
import { CopyButton, GhostButton, Modal, PrimaryButton, Spinner } from "./ui";

export function ShareModal({ tracePk, onClose }: { tracePk: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [expiry, setExpiry] = useState<string>("168");

  const shares = useQuery({
    queryKey: ["shares", tracePk],
    queryFn: () => api.listShares(tracePk),
  });

  const preview = useQuery({
    queryKey: ["share-preview", tracePk],
    queryFn: () => api.sharePreview(tracePk),
  });

  const create = useMutation({
    mutationFn: () =>
      api.createShare(tracePk, Number(expiry)),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["shares", tracePk] }),
  });

  const revoke = useMutation({
    mutationFn: (shareId: string) => api.revokeShare(shareId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["shares", tracePk] }),
  });

  const active = (shares.data ?? []).filter((s) => s.revoked_at === null);

  return (
    <Modal title="Share this trace" onClose={onClose}>
      <p className="mb-4 text-xs text-ink-muted">
        Anyone with the link can see the metrics below until it expires or is revoked.
      </p>

      {preview.data && <SharedMetrics trace={preview.data} />}
      {preview.isError && <p role="alert">Could not load share preview.</p>}
      {create.isError && <p role="alert">Could not create share link.</p>}
      <div className="mb-4 flex items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Expires
          <select
            value={expiry}
            onChange={(event) => setExpiry(event.target.value)}
            className="rounded-lg border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-ink"
          >
            <option value="24">in 24 hours</option>
            <option value="168">in 7 days</option>
            <option value="720">in 30 days</option>
          </select>
        </label>
        <PrimaryButton onClick={() => create.mutate()} disabled={create.isPending || !preview.data}>
          {create.isPending ? "Creating…" : "Create link"}
        </PrimaryButton>
      </div>

      {shares.isLoading ? (
        <Spinner />
      ) : active.length === 0 ? (
        <p className="text-xs text-ink-muted">No active links.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {active.map((share) => {
            const url = `${window.location.origin}/share#${share.token}`;
            return (
              <li
                key={share.id}
                className="flex items-center gap-2 rounded-lg border border-hairline px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="mono truncate text-xs" title={url}>
                    {url}
                  </p>
                  <p className="text-[11px] text-ink-muted">
                    created {formatTimeAgo(share.created_at)}
                    {share.expires_at
                      ? ` · expires ${new Date(share.expires_at).toLocaleDateString()}`
                      : " · never expires"}
                  </p>
                </div>
                <CopyButton text={url} label="Copy link" />
                <GhostButton
                  onClick={() => revoke.mutate(share.id)}
                  className="!px-2 !py-1 text-xs"
                >
                  Revoke
                </GhostButton>
              </li>
            );
          })}
        </ul>
      )}
    </Modal>
  );
}
