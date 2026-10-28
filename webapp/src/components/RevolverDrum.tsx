import React, { useState, useRef, useEffect, useCallback } from 'react';

interface RevolverDrumProps {
  value: string; // format "HH:MM"
  onChange: (newTime: string) => void;
  label?: string;
}

export const RevolverDrum: React.FC<RevolverDrumProps> = ({
  value,
  onChange,
  label = 'Время автоотчёта',
}) => {
  const [hours, setHours] = useState<number>(() => {
    const [h] = value.split(':').map(Number);
    return isNaN(h) ? 11 : h;
  });

  const [minutes, setMinutes] = useState<number>(() => {
    const [, m] = value.split(':').map(Number);
    return isNaN(m) ? 30 : m;
  });

  // Continuous visual drag angles (degrees)
  const [hourDragAngle, setHourDragAngle] = useState<number>(0);
  const [minuteDragAngle, setMinuteDragAngle] = useState<number>(0);
  const [isDraggingHour, setIsDraggingHour] = useState<boolean>(false);
  const [isDraggingMinute, setIsDraggingMinute] = useState<boolean>(false);
  const [minuteStepMode, setMinuteStepMode] = useState<5 | 1>(5);

  const hourViewportRef = useRef<HTMLDivElement | null>(null);
  const minuteViewportRef = useRef<HTMLDivElement | null>(null);

  // Audio Context for synthetic mechanical ratchet clicks
  const audioCtxRef = useRef<AudioContext | null>(null);

  const playRatchetClick = useCallback((heavy: boolean = false) => {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioCtx();
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === 'suspended') {
        ctx.resume();
      }
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      const t = ctx.currentTime;
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(heavy ? 550 : 850, t);
      osc.frequency.exponentialRampToValueAtTime(80, t + (heavy ? 0.035 : 0.02));
      gain.gain.setValueAtTime(heavy ? 0.16 : 0.08, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + (heavy ? 0.035 : 0.02));
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(t);
      osc.stop(t + (heavy ? 0.035 : 0.02));
    } catch {
      // ignore
    }
  }, []);

  const triggerHaptic = useCallback((heavy: boolean = false) => {
    try {
      // @ts-ignore
      const haptic = window.Telegram?.WebApp?.HapticFeedback;
      if (haptic) {
        if (heavy && haptic.impactOccurred) {
          haptic.impactOccurred('medium');
        } else if (haptic.selectionChanged) {
          haptic.selectionChanged();
        }
      }
    } catch {
      // ignore
    }
    playRatchetClick(heavy);
  }, [playRatchetClick]);

  // Keep state synced if prop changes externally
  useEffect(() => {
    const [h, m] = value.split(':').map(Number);
    if (!isNaN(h)) setHours(h);
    if (!isNaN(m)) setMinutes(m);
  }, [value]);

  const updateTime = useCallback((newH: number, newM: number, heavyLock: boolean = true) => {
    const safeH = (newH + 24) % 24;
    const safeM = (newM + 60) % 60;
    setHours(safeH);
    setMinutes(safeM);
    triggerHaptic(heavyLock);
    const formatted = `${String(safeH).padStart(2, '0')}:${String(safeM).padStart(2, '0')}`;
    onChange(formatted);
  }, [onChange, triggerHaptic]);

  const stepHour = useCallback((delta: number) => {
    updateTime(hours + delta, minutes, true);
  }, [hours, minutes, updateTime]);

  const stepMinute = useCallback((delta: number) => {
    updateTime(hours, minutes + delta, true);
  }, [hours, minutes, updateTime]);

  // Wheel handling with passive: false to prevent browser warning
  useEffect(() => {
    const hEl = hourViewportRef.current;
    if (!hEl) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      stepHour(e.deltaY > 0 ? 1 : -1);
    };
    hEl.addEventListener('wheel', handleWheel, { passive: false });
    return () => hEl.removeEventListener('wheel', handleWheel);
  }, [stepHour]);

  useEffect(() => {
    const mEl = minuteViewportRef.current;
    if (!mEl) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      stepMinute(e.deltaY > 0 ? (minuteStepMode === 5 ? 5 : 1) : (minuteStepMode === 5 ? -5 : -1));
    };
    mEl.addEventListener('wheel', handleWheel, { passive: false });
    return () => mEl.removeEventListener('wheel', handleWheel);
  }, [stepMinute, minuteStepMode]);

  // POINTER DRAG FOR HOURS CYLINDER
  const hourDragRef = useRef<{ startY: number; startHours: number; lastSteps: number } | null>(null);

  const handleHourPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    hourDragRef.current = {
      startY: e.clientY,
      startHours: hours,
      lastSteps: 0,
    };
    setIsDraggingHour(true);
    setHourDragAngle(0);
  };

  const handleHourPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!hourDragRef.current) return;
    const diffY = hourDragRef.current.startY - e.clientY;
    // 25px per 1 hour chamber step
    const steps = Math.trunc(diffY / 25);
    const angleDelta = (diffY % 25) * 0.9;
    setHourDragAngle(-angleDelta);

    if (steps !== hourDragRef.current.lastSteps) {
      triggerHaptic(false);
      hourDragRef.current.lastSteps = steps;
    }
  };

  const handleHourPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!hourDragRef.current) return;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
    const diffY = hourDragRef.current.startY - e.clientY;
    const steps = Math.round(diffY / 25);
    setIsDraggingHour(false);
    setHourDragAngle(0);
    const startH = hourDragRef.current.startHours;
    hourDragRef.current = null;
    if (steps !== 0) {
      updateTime(startH + steps, minutes, true);
    }
  };

  // POINTER DRAG FOR MINUTES CYLINDER
  const minuteDragRef = useRef<{ startY: number; startMinutes: number; lastSteps: number } | null>(null);

  const handleMinutePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    minuteDragRef.current = {
      startY: e.clientY,
      startMinutes: minutes,
      lastSteps: 0,
    };
    setIsDraggingMinute(true);
    setMinuteDragAngle(0);
  };

  const handleMinutePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!minuteDragRef.current) return;
    const diffY = minuteDragRef.current.startY - e.clientY;
    const stepSize = minuteStepMode === 5 ? 24 : 16;
    const steps = Math.trunc(diffY / stepSize);
    const angleDelta = (diffY % stepSize) * 0.9;
    setMinuteDragAngle(-angleDelta);

    if (steps !== minuteDragRef.current.lastSteps) {
      triggerHaptic(false);
      minuteDragRef.current.lastSteps = steps;
    }
  };

  const handleMinutePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!minuteDragRef.current) return;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
    const diffY = minuteDragRef.current.startY - e.clientY;
    const stepSize = minuteStepMode === 5 ? 24 : 16;
    const steps = Math.round(diffY / stepSize);
    const minuteIncrement = minuteStepMode === 5 ? 5 : 1;
    setIsDraggingMinute(false);
    setMinuteDragAngle(0);
    const startM = minuteDragRef.current.startMinutes;
    minuteDragRef.current = null;
    if (steps !== 0) {
      updateTime(hours, startM + steps * minuteIncrement, true);
    }
  };

  // Chambers distribution in 3D
  // 5 chambers visible at a time around current center
  const chamberOffsets = [-2, -1, 0, 1, 2];

  return (
    <div className="revolver-widget">
      <div className="revolver-header">
        <div className="revolver-title">
          <span>⚙️ БАРАБАН РЕВОЛЬВЕРА</span>
          <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>3D CYLINDER LOCK</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="revolver-target-tag">
            {String(hours).padStart(2, '0')}:{String(minutes).padStart(2, '0')} ЕКБ
          </span>
        </div>
      </div>

      <div className="revolver-assembly">
        {/* Ratchet Notch Lock (Пружинный зубчатый фиксатор барабана) */}
        <div className="ratchet-indicator">
          <div className="ratchet-pin-left" />
          <div className="ratchet-flute-glow" />
          <div className="ratchet-pin-right" />
        </div>

        {/* HOURS CYLINDER */}
        <div className="cylinder-unit">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', padding: '0 4px' }}>
            <span className="cylinder-label">ЧАСЫ (00–23)</span>
          </div>

          <div
            ref={hourViewportRef}
            className="drum-viewport"
            onPointerDown={handleHourPointerDown}
            onPointerMove={handleHourPointerMove}
            onPointerUp={handleHourPointerUp}
            onPointerCancel={handleHourPointerUp}
          >
            <div
              className="drum-rotor"
              style={{
                transform: `rotateX(${hourDragAngle}deg)`,
                transition: isDraggingHour ? 'none' : 'transform 0.22s cubic-bezier(0.2, 0.8, 0.25, 1)',
              }}
            >
              {chamberOffsets.map((offset) => {
                const hVal = (hours + offset + 24) % 24;
                const angle = offset * 26;
                const zDist = 112;
                const isActive = offset === 0;
                return (
                  <div
                    key={`h-${offset}`}
                    className={`chamber-cell ${isActive ? 'active-chamber' : ''}`}
                    style={{
                      transform: `rotateX(${-angle}deg) translateZ(${zDist}px)`,
                      opacity: isActive ? 1 : Math.max(0.18, 1 - Math.abs(offset) * 0.38),
                    }}
                    onClick={() => stepHour(offset)}
                  >
                    <div className="chamber-cartridge-rim" />
                    <span className="chamber-text">{String(hVal).padStart(2, '0')}</span>
                    {isActive && <div className="cartridge-primer" />}
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
              title="Час назад (-1ч)"
            >
              ▲
            </button>
            <button
              type="button"
              className="drum-step-btn"
              onClick={() => stepHour(1)}
              title="Час вперед (+1ч)"
            >
              ▼
            </button>
          </div>
        </div>

        {/* COLON SEPARATOR WITH MECHANICAL PIVOT */}
        <div className="drum-colon-box">
          <div className="drum-colon">:</div>
          <div className="drum-revolver-axis" title="Ось барабана" />
        </div>

        {/* MINUTES CYLINDER */}
        <div className="cylinder-unit">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', padding: '0 4px' }}>
            <span className="cylinder-label">МИНУТЫ (00–59)</span>
          </div>

          <div
            ref={minuteViewportRef}
            className="drum-viewport"
            onPointerDown={handleMinutePointerDown}
            onPointerMove={handleMinutePointerMove}
            onPointerUp={handleMinutePointerUp}
            onPointerCancel={handleMinutePointerUp}
          >
            <div
              className="drum-rotor"
              style={{
                transform: `rotateX(${minuteDragAngle}deg)`,
                transition: isDraggingMinute ? 'none' : 'transform 0.22s cubic-bezier(0.2, 0.8, 0.25, 1)',
              }}
            >
              {chamberOffsets.map((offset) => {
                const step = minuteStepMode === 5 ? 5 : 1;
                const mVal = (minutes + offset * step + 600) % 60;
                const angle = offset * 26;
                const zDist = 112;
                const isActive = offset === 0;
                return (
                  <div
                    key={`m-${offset}`}
                    className={`chamber-cell ${isActive ? 'active-chamber' : ''}`}
                    style={{
                      transform: `rotateX(${-angle}deg) translateZ(${zDist}px)`,
                      opacity: isActive ? 1 : Math.max(0.18, 1 - Math.abs(offset) * 0.38),
                    }}
                    onClick={() => stepMinute(offset * step)}
                  >
                    <div className="chamber-cartridge-rim" />
                    <span className="chamber-text">{String(mVal).padStart(2, '0')}</span>
                    {isActive && <div className="cartridge-primer" />}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="drum-controls">
            <button
              type="button"
              className="drum-step-btn"
              onClick={() => stepMinute(minuteStepMode === 5 ? -5 : -1)}
              title={minuteStepMode === 5 ? '-5 минут' : '-1 минута'}
            >
              ▲
            </button>
            <button
              type="button"
              className="drum-step-btn"
              onClick={() => stepMinute(minuteStepMode === 5 ? 5 : 1)}
              title={minuteStepMode === 5 ? '+5 минут' : '+1 минута'}
            >
              ▼
            </button>
          </div>
        </div>
      </div>

      {/* Step Mode Toggle & Quick Presets */}
      <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>ШАГ МИНУТ:</span>
          <button
            type="button"
            className={`dev-btn dev-btn-secondary ${minuteStepMode === 5 ? 'active' : ''}`}
            style={{
              padding: '2px 8px',
              fontSize: 10,
              borderColor: minuteStepMode === 5 ? '#58a6ff' : undefined,
              color: minuteStepMode === 5 ? '#58a6ff' : undefined,
            }}
            onClick={() => setMinuteStepMode(5)}
          >
            5 мин
          </button>
          <button
            type="button"
            className={`dev-btn dev-btn-secondary ${minuteStepMode === 1 ? 'active' : ''}`}
            style={{
              padding: '2px 8px',
              fontSize: 10,
              borderColor: minuteStepMode === 1 ? '#58a6ff' : undefined,
              color: minuteStepMode === 1 ? '#58a6ff' : undefined,
            }}
            onClick={() => setMinuteStepMode(1)}
          >
            1 мин (точно)
          </button>
        </div>

        {/* Quick Presets */}
        <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
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
                updateTime(h, m, true);
              }}
            >
              {preset}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
