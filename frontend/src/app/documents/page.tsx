"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { DocumentCard } from "@/components/DocumentCard";
import { UploadZone } from "@/components/UploadZone";
import {
  bulkMoveDocuments,
  createFolder,
  deleteDocument,
  deleteFolder,
  listDocumentPermissions,
  listDocuments,
  listFolders,
  moveDocument,
  revokeDocumentPermission,
  shareDocument,
  updateFolder,
  uploadDocument,
} from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { AccessRole, Document, Folder, PermissionEntry } from "@/lib/types";

export default function DocumentsPage() {
  const { user, loading, getIdToken } = useRequireAuth();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null);
  const [selectedDocs, setSelectedDocs] = useState<Record<string, boolean>>({});
  const [bulkTargetFolder, setBulkTargetFolder] = useState<string>("");
  const [newFolderName, setNewFolderName] = useState("");
  const [permissionsDoc, setPermissionsDoc] = useState<Document | null>(null);
  const [permissions, setPermissions] = useState<PermissionEntry[]>([]);
  const [shareEmail, setShareEmail] = useState("");
  const [shareRole, setShareRole] = useState<Exclude<AccessRole, "owner">>("viewer");

  const loadData = useCallback(async () => {
    if (!user) return;
    setError(null);
    try {
      const token = await getIdToken();
      if (!token) return;
      const [docs, folderRows] = await Promise.all([listDocuments(token), listFolders(token)]);
      setDocuments(docs);
      setFolders(folderRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed loading documents");
    }
  }, [user, getIdToken]);

  useEffect(() => {
    if (!loading && user) {
      void loadData();
    }
  }, [loading, user, loadData]);

  useEffect(() => {
    if (!documents.some((doc) => doc.status === "uploaded" || doc.status === "processing")) {
      return;
    }
    const id = setInterval(() => {
      void loadData();
    }, 5000);
    return () => clearInterval(id);
  }, [documents, loadData]);

  const visibleDocuments = useMemo(
    () => documents.filter((doc) => (activeFolderId ? doc.folder_id === activeFolderId : true)),
    [documents, activeFolderId],
  );

  const selectedDocumentIds = useMemo(
    () => Object.entries(selectedDocs).filter(([, checked]) => checked).map(([id]) => id),
    [selectedDocs],
  );

  const onUpload = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const token = await getIdToken();
      if (!token) return;
      await uploadDocument(file, token);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Upload failed for ${file.name}`);
    } finally {
      setBusy(false);
    }
  };

  const onCreateFolder = async () => {
    if (!newFolderName.trim()) return;
    try {
      const token = await getIdToken();
      if (!token) return;
      await createFolder({ name: newFolderName.trim() }, token);
      setNewFolderName("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed creating folder");
    }
  };

  const onRenameFolder = async (folder: Folder) => {
    const nextName = window.prompt("Rename folder", folder.name);
    if (!nextName || nextName === folder.name) return;
    try {
      const token = await getIdToken();
      if (!token) return;
      await updateFolder(folder.id, { name: nextName, color: folder.color, icon: folder.icon }, token);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed renaming folder");
    }
  };

  const onDeleteFolder = async (folder: Folder) => {
    if (!window.confirm(`Delete folder "${folder.name}"?`)) return;
    try {
      const token = await getIdToken();
      if (!token) return;
      await deleteFolder(folder.id, token);
      if (activeFolderId === folder.id) {
        setActiveFolderId(null);
      }
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed deleting folder");
    }
  };

  const onBulkMove = async () => {
    if (!selectedDocumentIds.length) return;
    try {
      const token = await getIdToken();
      if (!token) return;
      await bulkMoveDocuments(selectedDocumentIds, bulkTargetFolder || null, token);
      setSelectedDocs({});
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk move failed");
    }
  };

  const onOpenPermissions = async (doc: Document) => {
    setPermissionsDoc(doc);
    setPermissions([]);
    try {
      const token = await getIdToken();
      if (!token) return;
      const rows = await listDocumentPermissions(doc.id, token);
      setPermissions(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed loading permissions");
    }
  };

  const onShareDocument = async () => {
    if (!permissionsDoc || !shareEmail.trim()) return;
    try {
      const token = await getIdToken();
      if (!token) return;
      await shareDocument(permissionsDoc.id, shareEmail.trim(), shareRole, token);
      setShareEmail("");
      const rows = await listDocumentPermissions(permissionsDoc.id, token);
      setPermissions(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed sharing document");
    }
  };

  const onRevoke = async (permId: string) => {
    if (!permissionsDoc) return;
    try {
      const token = await getIdToken();
      if (!token) return;
      await revokeDocumentPermission(permissionsDoc.id, permId, token);
      setPermissions((prev) => prev.filter((perm) => perm.id !== permId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed revoking permission");
    }
  };

  if (loading || (!user && !loading)) {
    return <div className="p-6">Loading...</div>;
  }

  return (
    <AppShell
      title="Documents"
      folders={folders}
      activeFolderId={activeFolderId}
      onFolderClick={setActiveFolderId}
      actions={
        <button
          onClick={() => void loadData()}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100"
        >
          Refresh
        </button>
      }
    >
      <div className="grid grid-cols-1 xl:grid-cols-[2fr_1fr] gap-4">
        <section className="space-y-4">
          <UploadZone onUpload={onUpload} />
          {busy ? <p className="text-sm text-slate-500">Uploading...</p> : null}
          {error ? <p className="text-sm text-red-600">{error}</p> : null}

          <div className="rounded-xl border bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-semibold">Document Library</h2>
              <div className="flex items-center gap-2">
                <select
                  value={bulkTargetFolder}
                  onChange={(e) => setBulkTargetFolder(e.target.value)}
                  className="rounded border px-2 py-1 text-sm"
                >
                  <option value="">Move selected to Unfiled</option>
                  {folders.map((folder) => (
                    <option key={folder.id} value={folder.id}>
                      {folder.name}
                    </option>
                  ))}
                </select>
                <button
                  onClick={onBulkMove}
                  disabled={!selectedDocumentIds.length}
                  className="rounded bg-slate-900 text-white px-3 py-1.5 text-sm disabled:opacity-50"
                >
                  Bulk Move ({selectedDocumentIds.length})
                </button>
              </div>
            </div>

            <div className="mt-3 grid gap-3">
              {visibleDocuments.map((doc) => (
                <DocumentCard
                  key={doc.id}
                  document={doc}
                  selected={Boolean(selectedDocs[doc.id])}
                  onSelect={(checked) => setSelectedDocs((prev) => ({ ...prev, [doc.id]: checked }))}
                  onMove={(folderId) => {
                    void (async () => {
                      const token = await getIdToken();
                      if (!token) return;
                      await moveDocument(doc.id, folderId, token);
                      await loadData();
                    })();
                  }}
                  folderOptions={folders.map((folder) => ({ id: folder.id, name: folder.name }))}
                  onOpenPermissions={() => void onOpenPermissions(doc)}
                  onDelete={() => {
                    void (async () => {
                      if (!window.confirm(`Delete "${doc.name}"?`)) return;
                      const token = await getIdToken();
                      if (!token) return;
                      await deleteDocument(doc.id, token);
                      await loadData();
                    })();
                  }}
                />
              ))}
              {!visibleDocuments.length ? (
                <p className="text-sm text-slate-500">No documents yet in this view.</p>
              ) : null}
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <div className="rounded-xl border bg-white p-4">
            <h2 className="font-semibold">Folders</h2>
            <div className="mt-3 flex gap-2">
              <input
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                placeholder="New folder name"
                className="flex-1 rounded border px-3 py-2 text-sm"
              />
              <button onClick={onCreateFolder} className="rounded bg-blue-600 text-white px-3 py-2 text-sm">
                Add
              </button>
            </div>
            <div className="mt-3 space-y-2">
              {folders.map((folder) => (
                <div key={folder.id} className="rounded border p-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span>
                      {folder.icon} {folder.name} ({folder.doc_count ?? 0})
                    </span>
                    <div className="flex gap-2">
                      <button onClick={() => void onRenameFolder(folder)} className="text-blue-600">
                        Rename
                      </button>
                      <button onClick={() => void onDeleteFolder(folder)} className="text-red-600">
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border bg-white p-4">
            <h2 className="font-semibold">Document Permissions</h2>
            {permissionsDoc ? (
              <>
                <p className="mt-1 text-sm text-slate-600">Managing: {permissionsDoc.name}</p>
                <div className="mt-3 flex gap-2">
                  <input
                    value={shareEmail}
                    onChange={(e) => setShareEmail(e.target.value)}
                    placeholder="user@example.com"
                    className="flex-1 rounded border px-3 py-2 text-sm"
                  />
                  <select
                    value={shareRole}
                    onChange={(e) => setShareRole(e.target.value as Exclude<AccessRole, "owner">)}
                    className="rounded border px-2 py-2 text-sm"
                  >
                    <option value="viewer">viewer</option>
                    <option value="editor">editor</option>
                    <option value="admin">admin</option>
                  </select>
                  <button onClick={onShareDocument} className="rounded bg-slate-900 text-white px-3 py-2 text-sm">
                    Share
                  </button>
                </div>
                <div className="mt-3 space-y-2">
                  {permissions.map((perm) => (
                    <div key={perm.id} className="rounded border p-2 text-xs flex items-center justify-between">
                      <span>
                        {perm.email} · {perm.role}
                      </span>
                      <button onClick={() => void onRevoke(perm.id)} className="text-red-600">
                        Revoke
                      </button>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="mt-2 text-sm text-slate-500">Choose a document and click Permissions.</p>
            )}
          </div>
        </section>
      </div>
    </AppShell>
  );
}
