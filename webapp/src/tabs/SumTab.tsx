import React, { useState, useEffect } from 'react';

interface TicketItem {
  key: string;
  summary: string;
  status: string;
  url: string;
  comment_text?: string | null;
}

interface SummaryData {
  ok: boolean;
  date: string;
  display_name: string;
  account_id: string;
  andrey_mode: boolean;
  total_count: number;
  created: TicketItem[];
  transitioned: TicketItem[];
  commented: TicketItem[];
  raw_text: string;
}

interface SumTabProps {
  onNotify: (msg: string) => void;
}

export const SumTab: React.FC<SumTabProps> = ({ onNotify }) => {
  const [selectedDate, setSelectedDate] = useState<string>(() => {
    return new Date().toLocaleDateString('en-CA');
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [sending, setSending] = useState<boolean>(false);
  const [data, setData] = useState<SummaryData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = async (targetDate: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/sum?date=${targetDate}`);
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.error || 'Ошибка загрузки отчета');
      }
      setData(json);
    } catch (err: any) {
      setError(err.message || 'Ошибка сети');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary(selectedDate);
  }, [selectedDate]);

  const handleSendTelegram = async () => {
    setSending(true);
    try {
      const res = await fetch('/api/sum/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: selectedDate }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.error || 'Не удалось отправить отчёт');
      }
      onNotify('✓ Отчёт успешно отправлен в Telegram!');
    } catch (err: any) {
      onNotify(`⚠️ ${err.message}`);
    } finally {
      setSending(false);
    }
  };

  const getStatusClass = (status: string) => {
    const s = status.toLowerCase();
    if (s.includes('done') || s.includes('готов') || s.includes('закрыт') || s.includes('resolved')) return 'done';
    if (s.includes('progress') || s.includes('работе') || s.includes('review') || s.includes('тест')) return 'in-progress';
    return 'todo';
  };

  const getPresetDate = (daysAgo: number) => {
    const d = new Date();
    d.setDate(d.getDate() - daysAgo);
    return d.toLocaleDateString('en-CA');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Controls Card */}
      <div className="dev-card">
        <div className="dev-card-header">
          <span className="header-title">⚡ [SUM] ГЕНЕРАТОР ДЕЙЛИКОВ</span>
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>JIRA CLOUD</span>
        </div>
        <div className="dev-card-body">
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
            <button
              type="button"
              className={`dev-btn dev-btn-secondary ${selectedDate === getPresetDate(0) ? 'active' : ''}`}
              style={{ fontSize: 11, padding: '5px 10px' }}
              onClick={() => setSelectedDate(getPresetDate(0))}
            >
              Сегодня
            </button>
            <button
              type="button"
              className={`dev-btn dev-btn-secondary ${selectedDate === getPresetDate(1) ? 'active' : ''}`}
              style={{ fontSize: 11, padding: '5px 10px' }}
              onClick={() => setSelectedDate(getPresetDate(1))}
            >
              Вчера
            </button>
            <input
              type="date"
              className="dev-input"
              style={{ width: 'auto', padding: '4px 8px', fontSize: 11 }}
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
            />
            <button
              type="button"
              className="dev-btn dev-btn-secondary"
              style={{ fontSize: 11, padding: '5px 10px', marginLeft: 'auto' }}
              onClick={() => fetchSummary(selectedDate)}
              disabled={loading}
            >
              {loading ? '⏳' : '↻ Обновить'}
            </button>
          </div>

          {/* Quick Metrics */}
          {data && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginTop: 8 }}>
              <div style={{ background: 'var(--bg-inset)', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border-muted)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>ВСЕГО</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>{data.total_count}</div>
              </div>
              <div style={{ background: 'var(--bg-inset)', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border-muted)' }}>
                <div style={{ fontSize: 10, color: 'var(--accent-green)' }}>СОЗДАЛ</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent-green)' }}>{data.created.length}</div>
              </div>
              <div style={{ background: 'var(--bg-inset)', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border-muted)' }}>
                <div style={{ fontSize: 10, color: 'var(--accent-blue)' }}>СТАТУСЫ</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent-blue)' }}>{data.transitioned.length}</div>
              </div>
              <div style={{ background: 'var(--bg-inset)', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border-muted)' }}>
                <div style={{ fontSize: 10, color: 'var(--accent-yellow)' }}>КОММЕНТЫ</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent-yellow)' }}>{data.commented.length}</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div style={{ background: 'var(--accent-red-bg)', border: '1px solid rgba(248, 81, 73, 0.4)', padding: 12, borderRadius: 6, color: 'var(--accent-red)' }}>
          ⚠️ {error}
        </div>
      )}

      {/* Dispatch Action Button */}
      {data && (
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            type="button"
            className="dev-btn dev-btn-primary"
            style={{ flex: 1, padding: '10px 16px', fontSize: 13 }}
            onClick={handleSendTelegram}
            disabled={sending}
          >
            {sending ? '⏳ Отправка...' : '🚀 Отправить в Telegram DM'}
          </button>
          <button
            type="button"
            className="dev-btn dev-btn-secondary"
            onClick={() => {
              navigator.clipboard?.writeText(data.raw_text);
              onNotify('✓ Текст отчёта скопирован!');
            }}
          >
            📋 Копировать
          </button>
        </div>
      )}

      {/* Tickets Preview Feed */}
      {data && (
        <div className="dev-card">
          <div className="dev-card-header">
            <span>ПРЕДПРОСМОТР ТИКЕТОВ ({data.date})</span>
            <span style={{ color: 'var(--accent-blue)' }}>{data.display_name}</span>
          </div>

          {data.total_count === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>
              Нет активности в Jira за {data.date}
            </div>
          ) : (
            <div>
              {/* Transitioned */}
              {data.transitioned.length > 0 && (
                <div>
                  <div style={{ padding: '6px 12px', background: 'var(--bg-inset)', fontSize: 10, fontWeight: 700, color: 'var(--accent-blue)', borderBottom: '1px solid var(--border-muted)' }}>
                    СМЕНИЛ СТАТУС ({data.transitioned.length})
                  </div>
                  {data.transitioned.map((t) => (
                    <div key={t.key} className="ticket-row">
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <a href={t.url} target="_blank" rel="noreferrer" className="ticket-key">
                            {t.key}
                          </a>
                          <span className={`status-pill ${getStatusClass(t.status)}`}>{t.status}</span>
                        </div>
                        <div className="ticket-summary">{t.summary}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Created */}
              {data.created.length > 0 && (
                <div>
                  <div style={{ padding: '6px 12px', background: 'var(--bg-inset)', fontSize: 10, fontWeight: 700, color: 'var(--accent-green)', borderBottom: '1px solid var(--border-muted)' }}>
                    СОЗДАЛ ({data.created.length})
                  </div>
                  {data.created.map((t) => (
                    <div key={t.key} className="ticket-row">
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <a href={t.url} target="_blank" rel="noreferrer" className="ticket-key">
                            {t.key}
                          </a>
                          <span className={`status-pill ${getStatusClass(t.status)}`}>{t.status}</span>
                        </div>
                        <div className="ticket-summary">{t.summary}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Commented */}
              {data.commented.length > 0 && (
                <div>
                  <div style={{ padding: '6px 12px', background: 'var(--bg-inset)', fontSize: 10, fontWeight: 700, color: 'var(--accent-yellow)', borderBottom: '1px solid var(--border-muted)' }}>
                    КОММЕНТАРИИ ({data.commented.length})
                  </div>
                  {data.commented.map((t) => (
                    <div key={t.key} className="ticket-row">
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <a href={t.url} target="_blank" rel="noreferrer" className="ticket-key">
                            {t.key}
                          </a>
                          <span className={`status-pill ${getStatusClass(t.status)}`}>{t.status}</span>
                        </div>
                        <div className="ticket-summary">{t.summary}</div>
                        {t.comment_text && <div className="ticket-comment">💬 {t.comment_text}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
