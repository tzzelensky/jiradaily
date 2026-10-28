import React, { useState, useEffect } from 'react';

interface TeamMember {
  jira_account_id: string;
  jira_display_name: string;
}

interface TeamItem {
  id: string;
  name: string;
  owner_chat_id: string;
  members: TeamMember[];
  notify: boolean;
  created_at?: string;
}

interface JiraUserResult {
  account_id: string;
  display_name: string;
  email?: string | null;
}

interface TeamsTabProps {
  onNotify: (msg: string) => void;
}

export const TeamsTab: React.FC<TeamsTabProps> = ({ onNotify }) => {
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [newTeamName, setNewTeamName] = useState<string>('');
  const [creating, setCreating] = useState<boolean>(false);
  const [activeTeamId, setActiveTeamId] = useState<string | null>(null);

  // Live Jira search autocomplete
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [searchResults, setSearchResults] = useState<JiraUserResult[]>([]);
  const [searching, setSearching] = useState<boolean>(false);
  const [addingMember, setAddingMember] = useState<boolean>(false);

  const fetchTeams = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/teams');
      const json = await res.json();
      if (res.ok && json.ok) {
        setTeams(json.teams || []);
        if (json.teams && json.teams.length > 0 && !activeTeamId) {
          setActiveTeamId(json.teams[0].id);
        }
      }
    } catch {
      onNotify('⚠️ Не удалось загрузить команды');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeams();
  }, []);

  // Jira autocomplete debounce
  useEffect(() => {
    if (!searchQuery.trim() || searchQuery.trim().length < 2) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await fetch(`/api/jira/search?q=${encodeURIComponent(searchQuery.trim())}`);
        const json = await res.json();
        if (res.ok && json.ok) {
          setSearchResults(json.users || []);
        }
      } catch {
        // ignore
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleCreateTeam = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTeamName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch('/api/teams', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newTeamName.trim() }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.error || 'Ошибка создания');
      }
      onNotify(`✓ Команда «${json.team.name}» создана!`);
      setNewTeamName('');
      await fetchTeams();
      setActiveTeamId(json.team.id);
    } catch (err: any) {
      onNotify(`⚠️ ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  const handleAddMember = async (teamId: string, user: JiraUserResult) => {
    setAddingMember(true);
    try {
      const res = await fetch(`/api/teams/${teamId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jira_account_id: user.account_id,
          jira_display_name: user.display_name,
        }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.error || 'Не удалось добавить');
      }
      onNotify(`✓ ${user.display_name} добавлен в команду!`);
      setSearchQuery('');
      setSearchResults([]);
      await fetchTeams();
    } catch (err: any) {
      onNotify(`⚠️ ${err.message}`);
    } finally {
      setAddingMember(false);
    }
  };

  const handleRemoveMember = async (teamId: string, accountId: string, name: string) => {
    if (!confirm(`Удалить ${name} из команды?`)) return;
    try {
      const res = await fetch(`/api/teams/${teamId}/members/${accountId}`, {
        method: 'DELETE',
      });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.error || 'Не удалось удалить');
      }
      onNotify(`✓ ${name} удален из команды`);
      await fetchTeams();
    } catch (err: any) {
      onNotify(`⚠️ ${err.message}`);
    }
  };

  const handleDeleteTeam = async (teamId: string, teamName: string) => {
    if (!confirm(`Вы действительно хотите удалить команду «${teamName}»?`)) return;
    try {
      const res = await fetch(`/api/teams/${teamId}`, { method: 'DELETE' });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.error || 'Не удалось удалить');
      }
      onNotify(`✓ Команда «${teamName}» удалена`);
      await fetchTeams();
    } catch (err: any) {
      onNotify(`⚠️ ${err.message}`);
    }
  };

  const handleSendTeamReport = async (teamId: string) => {
    try {
      const res = await fetch(`/api/teams/${teamId}/send`, { method: 'POST' });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.error || 'Ошибка отправки');
      }
      onNotify(json.message || '✓ Командный отчёт отправлен в Telegram!');
    } catch (err: any) {
      onNotify(`⚠️ ${err.message}`);
    }
  };

  const selectedTeam = teams.find((t) => t.id === activeTeamId) || teams[0];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Team Header & Creation */}
      <div className="dev-card">
        <div className="dev-card-header">
          <span className="header-title">👥 [TEAMS] УПРАВЛЕНИЕ КОМАНДАМИ</span>
          <span>{teams.length} КОМАНД</span>
        </div>
        <div className="dev-card-body">
          <form onSubmit={handleCreateTeam} style={{ display: 'flex', gap: 8 }}>
            <input
              type="text"
              className="dev-input"
              placeholder="Название новой команды..."
              value={newTeamName}
              onChange={(e) => setNewTeamName(e.target.value)}
            />
            <button type="submit" className="dev-btn dev-btn-primary" disabled={creating || !newTeamName.trim()}>
              {creating ? '...' : '+ Создать'}
            </button>
          </form>

          {/* Teams Selector Tabs */}
          {teams.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
              {teams.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`dev-btn dev-btn-secondary ${activeTeamId === t.id ? 'active' : ''}`}
                  style={{
                    fontSize: 11,
                    padding: '4px 10px',
                    borderColor: activeTeamId === t.id ? 'var(--accent-blue)' : undefined,
                    color: activeTeamId === t.id ? 'var(--accent-blue)' : undefined,
                  }}
                  onClick={() => setActiveTeamId(t.id)}
                >
                  {t.name} ({t.members?.length || 0})
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Selected Team Details */}
      {selectedTeam && (
        <div className="dev-card">
          <div className="dev-card-header">
            <span>
              КОМАНДА: <strong style={{ color: 'var(--text-primary)' }}>{selectedTeam.name}</strong>
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                type="button"
                className="dev-btn dev-btn-primary"
                style={{ padding: '3px 8px', fontSize: 10 }}
                onClick={() => handleSendTeamReport(selectedTeam.id)}
              >
                🚀 Запуск отчета
              </button>
              <button
                type="button"
                className="dev-btn dev-btn-danger"
                style={{ padding: '3px 8px', fontSize: 10 }}
                onClick={() => handleDeleteTeam(selectedTeam.id, selectedTeam.name)}
              >
                ✕ Удалить
              </button>
            </div>
          </div>

          <div className="dev-card-body">
            {/* Live Autocomplete Member Search */}
            <div className="input-group" style={{ position: 'relative' }}>
              <label className="input-label">Добавить Jira-участника (живой поиск)</label>
              <input
                type="text"
                className="dev-input"
                placeholder="Введи имя сотрудника (например, Тимофей)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />

              {searching && (
                <div style={{ position: 'absolute', right: 10, top: 28, fontSize: 11, color: 'var(--text-muted)' }}>
                  Поиск...
                </div>
              )}

              {/* Autocomplete Dropdown List */}
              {searchResults.length > 0 && (
                <div
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    zIndex: 40,
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-focus)',
                    borderRadius: 6,
                    marginTop: 4,
                    boxShadow: '0 8px 20px rgba(0,0,0,0.6)',
                    maxHeight: 200,
                    overflowY: 'auto',
                  }}
                >
                  {searchResults.map((u) => (
                    <div
                      key={u.account_id}
                      style={{
                        padding: '8px 12px',
                        borderBottom: '1px solid var(--border-muted)',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                      onClick={() => handleAddMember(selectedTeam.id, u)}
                    >
                      <div>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{u.display_name}</div>
                        {u.email && <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{u.email}</div>}
                      </div>
                      <span className="dev-btn dev-btn-secondary" style={{ padding: '2px 6px', fontSize: 10 }}>
                        + Добавить
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Members List */}
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 8 }}>
                СОСТАВ КОМАНДЫ ({selectedTeam.members?.length || 0}):
              </div>

              {(!selectedTeam.members || selectedTeam.members.length === 0) ? (
                <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)', background: 'var(--bg-inset)', borderRadius: 6 }}>
                  В команде пока нет участников. Найди и добавь коллег выше.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {selectedTeam.members.map((m, idx) => (
                    <div
                      key={m.jira_account_id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 12px',
                        background: 'var(--bg-inset)',
                        border: '1px solid var(--border-muted)',
                        borderRadius: 6,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{idx + 1}.</span>
                        <strong style={{ color: 'var(--text-primary)' }}>{m.jira_display_name}</strong>
                      </div>
                      <button
                        type="button"
                        className="dev-btn dev-btn-danger"
                        style={{ padding: '2px 6px', fontSize: 10 }}
                        onClick={() => handleRemoveMember(selectedTeam.id, m.jira_account_id, m.jira_display_name)}
                        title="Удалить из команды"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
