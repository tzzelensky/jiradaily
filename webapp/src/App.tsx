import React, { useState, useEffect } from 'react';
import { SumTab } from './tabs/SumTab';
import { TeamsTab } from './tabs/TeamsTab';
import { UsersTab } from './tabs/UsersTab';
import { ConfTab } from './tabs/ConfTab';

type TabType = 'sum' | 'teams' | 'users' | 'conf';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('sum');
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);

  useEffect(() => {
    // Expand Telegram WebApp & set theme colors
    try {
      // @ts-ignore
      const tg = window.Telegram?.WebApp;
      if (tg) {
        tg.ready();
        tg.expand();
        if (tg.setHeaderColor) tg.setHeaderColor('#0d1117');
        if (tg.setBackgroundColor) tg.setBackgroundColor('#0d1117');
      }
    } catch {
      // ignore
    }

    // Fetch user info
    fetch('/api/me')
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) setCurrentUser(data);
      })
      .catch(() => {});
  }, []);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3200);
  };

  return (
    <div className="app-shell">
      {/* Toast Bar */}
      {toastMessage && <div className="toast-bar">{toastMessage}</div>}

      {/* Top Header */}
      <header className="top-nav">
        <div className="top-brand">
          <span>@jirasumbot</span>
          <span className="badge">CODEX</span>
        </div>
        <div className="user-pill">
          <span className="dot" />
          <span>{currentUser?.jira_display_name || 'Admin'}</span>
        </div>
      </header>

      {/* Active Tab Screen */}
      <main className="page-content">
        {activeTab === 'sum' && <SumTab onNotify={showToast} />}
        {activeTab === 'teams' && <TeamsTab onNotify={showToast} />}
        {activeTab === 'users' && <UsersTab onNotify={showToast} />}
        {activeTab === 'conf' && <ConfTab onNotify={showToast} />}
      </main>

      {/* Bottom Bar Navigation */}
      <nav className="tab-bar">
        <div className="tab-bar-inner">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'sum' ? 'active' : ''}`}
            onClick={() => setActiveTab('sum')}
          >
            <span className="tab-code">[SUM]</span>
            <span>Дейлик</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'teams' ? 'active' : ''}`}
            onClick={() => setActiveTab('teams')}
          >
            <span className="tab-code">[TEAMS]</span>
            <span>Команды</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'users' ? 'active' : ''}`}
            onClick={() => setActiveTab('users')}
          >
            <span className="tab-code">[USERS]</span>
            <span>Инвайты</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'conf' ? 'active' : ''}`}
            onClick={() => setActiveTab('conf')}
          >
            <span className="tab-code">[CONF]</span>
            <span>Барабан</span>
          </button>
        </div>
      </nav>
    </div>
  );
};
export default App;
