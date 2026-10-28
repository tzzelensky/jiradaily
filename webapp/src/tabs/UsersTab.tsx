import React, { useState, useEffect } from 'react';

interface UserItem {
  chat_id: string;
  role: string;
  authorized: boolean;
  jira_account_id?: string | null;
  jira_display_name?: string | null;
  notify?: boolean;
  andrey_mode?: boolean;
  can_create_team?: boolean;
  invite_label?: string | null;
}

interface InviteItem {
  token: string;
  label?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  used_by?: string | null;
  used_at?: string | null;
  is_used: boolean;
  link: string;
}

interface UsersTabProps {
  onNotify: (msg: string) => void;
}

export const UsersTab: React.FC<UsersTabProps> = ({ onNotify }) => {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [invites, setInvites] = useState<InviteItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [label, setLabel] = useState<string>('');
  const [generating, setGenerating] = useState<boolean>(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [uRes, iRes] = await Promise.all([fetch('/api/users'), fetch('/api/invites')]);
      const uJson = await uRes.json();
      const iJson = await iRes.json();
      if (uJson.ok) setUsers(uJson.users || []);
      if (iJson.ok) setInvites(iJson.invites || []);
    } catch {
      onNotify('⚠️ Не удалось загрузить данные пользователей');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleGenerateInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setGenerating(true);
    try {
      const res = await fetch('/api/invites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: label.trim() || 'WebApp Invite' }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.error || 'Ошибка создания инвайта');
      }
      onNotify('✓ Инвайт-ссылка сгенерирована!');
      setLabel('');
      await fetchData();
    } catch (err: any) {
      onNotify(`⚠️ ${err.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard?.writeText(text);
    onNotify('✓ Ссылка скопирована в буфер обмена!');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Invite Generator Card */}
      <div className="dev-card">
        <div className="dev-card-header">
          <span className="header-title">🔑 [USERS] ГЕНЕРАТОР ИНВАЙТ-ТОКЕНОВ</span>
          <span>1-CLICK INVITE</span>
        </div>
        <div className="dev-card-body">
          <form onSubmit={handleGenerateInvite} style={{ display: 'flex', gap: 8 }}>
            <input
              type="text"
              className="dev-input"
              placeholder="Метка инвайта (например: 'Для Андрея', 'Frontend QA')..."
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
            <button type="submit" className="dev-btn dev-btn-primary" disabled={generating}>
              {generating ? '...' : '⚡ Создать ссылку'}
            </button>
          </form>
        </div>
      </div>

      {/* Invites List */}
      <div className="dev-card">
        <div className="dev-card-header">
          <span>ИНВАЙТ-ТОКЕНЫ ({invites.length})</span>
          <button type="button" className="dev-btn dev-btn-secondary" style={{ padding: '2px 8px', fontSize: 10 }} onClick={fetchData}>
            ↻ Обновить
          </button>
        </div>
        <div className="dev-card-body" style={{ padding: 0 }}>
          {invites.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)' }}>
              Нет активных инвайт-токенов. Создай первый выше.
            </div>
          ) : (
            <div>
              {invites.map((inv) => (
                <div
                  key={inv.token}
                  style={{
                    padding: '10px 14px',
                    borderBottom: '1px solid var(--border-muted)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 12,
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <strong style={{ color: 'var(--text-primary)', fontSize: 12 }}>{inv.label || 'Инвайт'}</strong>
                      <span className={`status-pill ${inv.is_used ? 'done' : 'in-progress'}`}>
                        {inv.is_used ? 'ИСПОЛЬЗОВАН' : 'АКТИВЕН'}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--accent-blue)', marginTop: 2, wordBreak: 'break-all' }}>
                      {inv.link}
                    </div>
                    {inv.used_by && (
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                        Активировал Telegram ID: {inv.used_by}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    className="dev-btn dev-btn-secondary"
                    style={{ padding: '4px 8px', fontSize: 11, flexShrink: 0 }}
                    onClick={() => copyToClipboard(inv.link)}
                  >
                    Копировать
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Authorized Users Table */}
      <div className="dev-card">
        <div className="dev-card-header">
          <span>АВТОРИЗОВАННЫЕ ПОЛЬЗОВАТЕЛИ ({users.length})</span>
          <span style={{ color: 'var(--accent-green)' }}>ONLINE</span>
        </div>
        <div className="dev-card-body" style={{ padding: 0 }}>
          {users.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)' }}>
              Нет авторизованных пользователей в базе.
            </div>
          ) : (
            <div>
              {users.map((u) => (
                <div
                  key={u.chat_id}
                  style={{
                    padding: '10px 14px',
                    borderBottom: '1px solid var(--border-muted)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <strong style={{ color: 'var(--text-primary)' }}>
                        {u.jira_display_name || 'Без Jira-имени'}
                      </strong>
                      <span className={`status-pill ${u.role === 'admin' ? 'done' : 'todo'}`}>
                        {u.role.toUpperCase()}
                      </span>
                      {u.andrey_mode && <span className="status-pill in-progress">АНДРЕЙ-MODE</span>}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                      TG ID: <code>{u.chat_id}</code> {u.invite_label ? `· [${u.invite_label}]` : ''}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span className={`status-pill ${u.notify !== false ? 'done' : 'todo'}`}>
                      {u.notify !== false ? 'NOTIFY ON' : 'NOTIFY OFF'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
