import React, { useState, useEffect } from 'react';
import { RevolverDrum } from '../components/RevolverDrum';

interface HealthData {
  ok: boolean;
  status: string;
  latency_ms: number;
  jira_base: string;
  jira_email: string;
  display_name?: string;
  account_id?: string;
  error?: string;
}

interface ScheduleConfig {
  personal_time: string;
  team_time: string;
  timezone: string;
}

interface LogEntry {
  time: string;
  level: string;
  msg: string;
}

interface ConfTabProps {
  onNotify: (msg: string) => void;
}

export const ConfTab: React.FC<ConfTabProps> = ({ onNotify }) => {
  const [config, setConfig] = useState<ScheduleConfig>({
    personal_time: '11:30',
    team_time: '12:00',
    timezone: 'Asia/Yekaterinburg',
  });
  const [activeDrumTarget, setActiveDrumTarget] = useState<'personal' | 'team'>('personal');
  const [savingConfig, setSavingConfig] = useState<boolean>(false);

  // Healthcheck state
  const [health, setHealth] = useState<HealthData | null>(null);
  const [checkingHealth, setCheckingHealth] = useState<boolean>(false);

  // Logs state
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loadingLogs, setLoadingLogs] = useState<boolean>(false);

  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/config');
      const json = await res.json();
      if (res.ok && json.ok && json.config) {
        setConfig(json.config);
      }
    } catch {
      // ignore
    }
  };

  const checkHealth = async () => {
    setCheckingHealth(true);
    try {
      const res = await fetch('/api/health');
      const json = await res.json();
      setHealth(json);
      if (json.ok) {
        onNotify(`✓ Jira активна! Пинг: ${json.latency_ms} мс`);
      } else {
        onNotify(`⚠️ Ошибка Jira: ${json.error || 'нет связи'}`);
      }
    } catch (err: any) {
      setHealth({
        ok: false,
        status: 'error',
        latency_ms: 0,
        jira_base: '',
        jira_email: '',
        error: err.message,
      });
      onNotify(`⚠️ Ошибка проверки: ${err.message}`);
    } finally {
      setCheckingHealth(false);
    }
  };

  const fetchLogs = async () => {
    setLoadingLogs(true);
    try {
      const res = await fetch('/api/logs');
      const json = await res.json();
      if (res.ok && json.ok) {
        setLogs(json.logs || []);
      }
    } catch {
      // ignore
    } finally {
      setLoadingLogs(false);
    }
  };

  useEffect(() => {
    fetchConfig();
    checkHealth();
    fetchLogs();
  }, []);

  const handleSaveConfig = async () => {
    setSavingConfig(true);
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          personal_time: config.personal_time,
          team_time: config.team_time,
        }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.error || 'Ошибка сохранения времени');
      }
      onNotify('✓ График автоотчётов успешно сохранен!');
    } catch (err: any) {
      onNotify(`⚠️ ${err.message}`);
    } finally {
      setSavingConfig(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 3D Revolver Drum Time Scheduler */}
      <div className="dev-card">
        <div className="dev-card-header">
          <span className="header-title">🔫 [CONF] ПЛАНИРОВЩИК АВТООТЧЕТОВ</span>
          <span>REVOLVER DRUM</span>
        </div>
        <div className="dev-card-body">
          {/* Target Selector: Personal vs Team */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button
              type="button"
              className={`dev-btn dev-btn-secondary ${activeDrumTarget === 'personal' ? 'active' : ''}`}
              style={{
                flex: 1,
                borderColor: activeDrumTarget === 'personal' ? 'var(--accent-blue)' : undefined,
                color: activeDrumTarget === 'personal' ? 'var(--accent-blue)' : undefined,
                background: activeDrumTarget === 'personal' ? 'var(--accent-blue-bg)' : undefined,
              }}
              onClick={() => setActiveDrumTarget('personal')}
            >
              Личный: {config.personal_time}
            </button>
            <button
              type="button"
              className={`dev-btn dev-btn-secondary ${activeDrumTarget === 'team' ? 'active' : ''}`}
              style={{
                flex: 1,
                borderColor: activeDrumTarget === 'team' ? 'var(--accent-blue)' : undefined,
                color: activeDrumTarget === 'team' ? 'var(--accent-blue)' : undefined,
                background: activeDrumTarget === 'team' ? 'var(--accent-blue-bg)' : undefined,
              }}
              onClick={() => setActiveDrumTarget('team')}
            >
              Команда: {config.team_time}
            </button>
          </div>

          {/* Interactive 3D Revolver Cylinder */}
          <RevolverDrum
            value={activeDrumTarget === 'personal' ? config.personal_time : config.team_time}
            label={activeDrumTarget === 'personal' ? 'Личный отчёт' : 'Отчёт команды'}
            onChange={(newTime) => {
              if (activeDrumTarget === 'personal') {
                setConfig((prev) => ({ ...prev, personal_time: newTime }));
              } else {
                setConfig((prev) => ({ ...prev, team_time: newTime }));
              }
            }}
          />

          <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              Часовой пояс: <strong style={{ color: 'var(--text-primary)' }}>{config.timezone} (Пн–Пт)</strong>
            </div>
            <button
              type="button"
              className="dev-btn dev-btn-primary"
              onClick={handleSaveConfig}
              disabled={savingConfig}
            >
              {savingConfig ? '⏳ Сохранение...' : '💾 Зафиксировать время'}
            </button>
          </div>
        </div>
      </div>

      {/* Jira Cloud Healthcheck Card */}
      <div className="dev-card">
        <div className="dev-card-header">
          <span>ДИАГНОСТИКА JIRA CLOUD</span>
          <button
            type="button"
            className="dev-btn dev-btn-secondary"
            style={{ padding: '2px 8px', fontSize: 10 }}
            onClick={checkHealth}
            disabled={checkingHealth}
          >
            {checkingHealth ? '⏳...' : '↻ Тест связи'}
          </button>
        </div>
        <div className="dev-card-body">
          {health ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Статус подключения:</span>
                <span className={`status-pill ${health.ok ? 'done' : 'todo'}`}>
                  {health.ok ? 'ПОДКЛЮЧЕНО' : 'ОШИБКА'}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Задержка API (Latency):</span>
                <strong style={{ color: health.ok ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                  {health.latency_ms} мс
                </strong>
              </div>
              {health.jira_base && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Базовый URL:</span>
                  <code style={{ color: 'var(--text-primary)' }}>{health.jira_base}</code>
                </div>
              )}
              {health.display_name && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Аккаунт Jira:</span>
                  <strong style={{ color: 'var(--text-primary)' }}>{health.display_name}</strong>
                </div>
              )}
              {health.error && (
                <div style={{ marginTop: 6, padding: 8, background: 'var(--accent-red-bg)', borderRadius: 4, color: 'var(--accent-red)', fontSize: 11 }}>
                  {health.error}
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 8 }}>
              Проверка состояния...
            </div>
          )}
        </div>
      </div>

      {/* Log Viewer Card */}
      <div className="dev-card">
        <div className="dev-card-header">
          <span>СИСТЕМНЫЙ ЖУРНАЛ СОБЫТИЙ (@jirasumbot)</span>
          <button
            type="button"
            className="dev-btn dev-btn-secondary"
            style={{ padding: '2px 8px', fontSize: 10 }}
            onClick={fetchLogs}
            disabled={loadingLogs}
          >
            ↻ Обновить
          </button>
        </div>
        <div
          className="dev-card-body"
          style={{
            padding: 0,
            maxHeight: 220,
            overflowY: 'auto',
            background: 'var(--bg-inset)',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
          }}
        >
          {logs.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)' }}>
              Журнал событий пуст или ожидает действий.
            </div>
          ) : (
            <div style={{ padding: '8px 12px' }}>
              {logs.slice().reverse().map((l, idx) => (
                <div key={idx} style={{ padding: '3px 0', borderBottom: '1px solid #161b22', display: 'flex', gap: 8 }}>
                  <span style={{ color: '#8b949e', flexShrink: 0 }}>[{l.time}]</span>
                  <span
                    style={{
                      color: l.level === 'ERROR' ? '#f85149' : l.level === 'WARNING' ? '#d29922' : '#58a6ff',
                      fontWeight: 700,
                      flexShrink: 0,
                    }}
                  >
                    {l.level}
                  </span>
                  <span style={{ color: '#c9d1d9', wordBreak: 'break-all' }}>{l.msg}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
