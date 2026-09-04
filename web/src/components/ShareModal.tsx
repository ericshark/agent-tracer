import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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

  const create = useMutation({
    mutationFn: () =>
      api.createShare(tracePk, expiry === "never" ? undefined : Number(expiry)),
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
        Anyone with the link gets a read-only view of this trace — no account needed, nothing
        else in the project is visible. Links use unguessable 256-bit tokens and can be revoked
        at any time.
      </p>

      <div className="mb-4 flex items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Expires
          <select
            value={expiry}
            onChange={(event) => setExpiry(event.target.value)}
            className="rounded-md border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-ink"
          >
            <option value="24">in 24 hours</option>
            <option value="168">in 7 days</option>
            <option value="720">in 30 days</option>
            <option value="never">never</option>
          </select>
        </label>
        <PrimaryButton onClick={() => create.mutate()} disabled={create.isPending}>
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
            const url = `${window.location.origin}/share/${share.token}`;
            return (
              <li
                key={share.id}
                className="flex items-center gap-2 rounded-md border border-hairline px-3 py-2"
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
