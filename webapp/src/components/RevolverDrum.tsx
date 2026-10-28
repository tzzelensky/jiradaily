import React, { useState, useRef, useEffect } from 'react';

interface RevolverDrumProps {
  value: string; // format "HH:MM"
  onChange: (newTime: string) => void;
  label?: string;
}

export const RevolverDrum: React.FC<RevolverDrumProps> = ({ value, onChange, label = 'Время автоотчёта' }) => {
  const [hours, setHours] = useState<number>(() => {
    const [h] = value.split(':').map(Number);
    return isNaN(h) ? 11 : h;
  });

  const [minutes, setMinutes] = useState<number>(() => {
    const [, m] = value.split(':').map(Number);
    return isNaN(m) ? 30 : m;
  });

  // Keep state synced if prop changes externally
  useEffect(() => {
    const [h, m] = value.split(':').map(Number);
    if (!isNaN(h)) setHours(h);
    if (!isNaN(m)) setMinutes(m);
  }, [value]);

  const triggerHaptic = () => {
    try {
      // @ts-ignore
      const haptic = window.Telegram?.WebApp?.HapticFeedback;
      if (haptic) {
        haptic.selectionChanged();
      }
    } catch {
      // ignore
    }
  };

  const updateTime = (newH: number, newM: number) => {
    const safeH = (newH + 24) % 24;
    const safeM = (newM + 60) % 60;
    setHours(safeH);
    setMinutes(safeM);
    triggerHaptic();
    const formatted = `${String(safeH).padStart(2, '0')}:${String(safeM).padStart(2, '0')}`;
    onChange(formatted);
  };

  const stepHour = (delta: number) => {
    updateTime(hours + delta, minutes);
  };

  const stepMinute = (delta: number) => {
    updateTime(hours, minutes + delta);
  };

  // Cylinder 3D chamber count
  // We project a local window of 5 visible chambers around the current value
  const hourOffsets = [-2, -1, 0, 1, 2];
  const minuteOffsets = [-2, -1, 0, 1, 2];

  // Drag handlers for touch / mouse
  const touchStartY = useRef<number | null>(null);
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY;
  };

  const handleTouchEndHour = (e: React.TouchEvent) => {
    if (touchStartY.current === null) return;
    const diff = touchStartY.current - e.changedTouches[0].clientY;
    if (Math.abs(diff) > 20) {
      stepHour(diff > 0 ? 1 : -1);
    }
    touchStartY.current = null;
  };

  const handleTouchEndMinute = (e: React.TouchEvent) => {
    if (touchStartY.current === null) return;
    const diff = touchStartY.current - e.changedTouches[0].clientY;
    if (Math.abs(diff) > 20) {
      stepMinute(diff > 0 ? 5 : -5);
    }
    touchStartY.current = null;
  };

  return (
    <div className="revolver-widget">
      <div className="revolver-header">
        <div className="revolver-title">
          <span>⚙️ БАРАБАН РЕВОЛЬВЕРА</span>
        </div>
        <span className="revolver-target-tag">
          {String(hours).padStart(2, '0')}:{String(minutes).padStart(2, '0')} ЕКБ
        </span>
      </div>

      <div className="revolver-assembly">
        {/* Ratchet Notch Lock (Зубец фиксатора) */}
        <div className="ratchet-indicator">
          <div className="ratchet-pin-left" />
          <div className="ratchet-pin-right" />
        </div>

        {/* HOURS CYLINDER */}
        <div className="cylinder-unit">
          <span className="cylinder-label">ЧАСЫ (00-23)</span>
          <div
            className="drum-viewport"
            onTouchStart={handleTouchStart}
            onTouchEnd={handleTouchEndHour}
            onWheel={(e) => {
              e.preventDefault();
              stepHour(e.deltaY > 0 ? 1 : -1);
            }}
          >
            <div className="drum-rotor">
              {hourOffsets.map((offset) => {
                const hVal = (hours + offset + 24) % 24;
                const angle = offset * 28;
                const zDist = 110;
                return (
                  <div
                    key={`h-${offset}`}
                    className={`chamber-cell ${offset === 0 ? 'active-chamber' : ''}`}
                    style={{
                      transform: `rotateX(${-angle}deg) translateZ(${zDist}px)`,
                      opacity: offset === 0 ? 1 : Math.max(0.15, 1 - Math.abs(offset) * 0.4),
                    }}
                    onClick={() => stepHour(offset)}
                  >
                    {String(hVal).padStart(2, '0')}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="drum-controls">
            <button
              type="button"
              className="drum-step-btn"
              onClick={() => stepHour(-1)}
              title="Час назад"
            >
              ▲
            </button>
            <button
              type="button"
              className="drum-step-btn"
              onClick={() => stepHour(1)}
              title="Час вперед"
            >
              ▼
            </button>
          </div>
        </div>

        {/* COLON */}
        <div className="drum-colon">:</div>

        {/* MINUTES CYLINDER */}
        <div className="cylinder-unit">
          <span className="cylinder-label">МИНУТЫ (00-59)</span>
          <div
            className="drum-viewport"
            onTouchStart={handleTouchStart}
            onTouchEnd={handleTouchEndMinute}
            onWheel={(e) => {
              e.preventDefault();
              stepMinute(e.deltaY > 0 ? 5 : -5);
            }}
          >
            <div className="drum-rotor">
              {minuteOffsets.map((offset) => {
                const mVal = (minutes + offset * 5 + 60) % 60;
                const angle = offset * 28;
                const zDist = 110;
                return (
                  <div
                    key={`m-${offset}`}
                    className={`chamber-cell ${offset === 0 ? 'active-chamber' : ''}`}
                    style={{
                      transform: `rotateX(${-angle}deg) translateZ(${zDist}px)`,
                      opacity: offset === 0 ? 1 : Math.max(0.15, 1 - Math.abs(offset) * 0.4),
                    }}
                    onClick={() => stepMinute(offset * 5)}
                  >
                    {String(mVal).padStart(2, '0')}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="drum-controls">
            <button
              type="button"
              className="drum-step-btn"
              onClick={() => stepMinute(-5)}
              title="-5 минут"
            >
              ▲
            </button>
            <button
              type="button"
              className="drum-step-btn"
              onClick={() => stepMinute(5)}
              title="+5 минут"
            >
              ▼
            </button>
          </div>
        </div>
      </div>

      {/* Quick Presets */}
      <div style={{ marginTop: 12, display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
        {['09:00', '10:00', '11:00', '11:30', '12:00', '18:00'].map((preset) => (
          <button
            key={preset}
            type="button"
            className="dev-btn dev-btn-secondary"
            style={{
              padding: '3px 8px',
              fontSize: 10,
              backgroundColor: value === preset ? 'rgba(88, 166, 255, 0.2)' : undefined,
              borderColor: value === preset ? '#58a6ff' : undefined,
              color: value === preset ? '#58a6ff' : undefined,
            }}
            onClick={() => {
              const [h, m] = preset.split(':').map(Number);
              updateTime(h, m);
            }}
          >
            {preset}
          </button>
        ))}
      </div>
    </div>
  );
};
