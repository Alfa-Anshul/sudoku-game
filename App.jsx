import React, { useState, useEffect, useCallback, useRef } from 'react';
import { generateFullBoard, createPuzzle, isValid, getHint, TIPS } from './sudoku';
import './App.css';

const DIFFICULTIES = { Easy: 42, Medium: 32, Hard: 24 };

function usePrevious(value) {
  const ref = useRef();
  useEffect(() => { ref.current = value; });
  return ref.current;
}

export default function App() {
  const [difficulty, setDifficulty] = useState('Medium');
  const [solution, setSolution] = useState(null);
  const [board, setBoard] = useState(null);
  const [locked, setLocked] = useState({});
  const [selected, setSelected] = useState(null);
  const [errors, setErrors] = useState({});
  const [hinted, setHinted] = useState({});
  const [won, setWon] = useState(false);
  const [timer, setTimer] = useState(0);
  const [running, setRunning] = useState(false);
  const [notes, setNotes] = useState({});
  const [noteMode, setNoteMode] = useState(false);
  const [hintCount, setHintCount] = useState(0);
  const [tipIdx, setTipIdx] = useState(0);
  const [history, setHistory] = useState([]);
  const [shake, setShake] = useState(null);
  const [justWon, setJustWon] = useState(false);

  const newGame = useCallback((diff) => {
    const d = diff || difficulty;
    const full = generateFullBoard();
    const puz = createPuzzle(full, DIFFICULTIES[d]);
    const lk = {};
    for (let r = 0; r < 9; r++)
      for (let c = 0; c < 9; c++)
        if (puz[r][c] !== 0) lk[`${r}-${c}`] = true;
    setSolution(full);
    setBoard(puz.map(r => [...r]));
    setLocked(lk);
    setSelected(null);
    setErrors({});
    setHinted({});
    setWon(false);
    setJustWon(false);
    setTimer(0);
    setRunning(true);
    setNotes({});
    setNoteMode(false);
    setHintCount(0);
    setHistory([]);
    setTipIdx(Math.floor(Math.random() * TIPS.length));
  }, [difficulty]);

  useEffect(() => { newGame(); }, []);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTimer(t => t + 1), 1000);
    return () => clearInterval(id);
  }, [running]);

  const fmt = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  const handleCell = (r, c) => {
    if (won) return;
    setSelected([r, c]);
  };

  const handleInput = (num) => {
    if (!selected || won) return;
    const [r, c] = selected;
    if (locked[`${r}-${c}`]) return;

    if (noteMode && num !== 0) {
      const key = `${r}-${c}`;
      setNotes(prev => {
        const cur = new Set(prev[key] || []);
        cur.has(num) ? cur.delete(num) : cur.add(num);
        return { ...prev, [key]: cur };
      });
      return;
    }

    // save history
    setHistory(h => [...h, { board: board.map(r => [...r]), errors: { ...errors }, notes: { ...notes } }]);

    const nb = board.map(row => [...row]);
    nb[r][c] = num === nb[r][c] ? 0 : num;
    const ne = { ...errors };
    delete ne[`${r}-${c}`];
    if (num !== 0 && solution && nb[r][c] !== solution[r][c]) {
      ne[`${r}-${c}`] = true;
      setShake(`${r}-${c}`);
      setTimeout(() => setShake(null), 400);
    }
    setBoard(nb);
    setErrors(ne);
    setNotes(prev => { const n = { ...prev }; delete n[`${r}-${c}`]; return n; });

    if (solution) {
      const complete = nb.every((row, ri) => row.every((v, ci) => v !== 0 && v === solution[ri][ci]));
      if (complete) { setWon(true); setJustWon(true); setRunning(false); }
    }
  };

  const handleUndo = () => {
    if (!history.length) return;
    const last = history[history.length - 1];
    setBoard(last.board);
    setErrors(last.errors);
    setNotes(last.notes);
    setHistory(h => h.slice(0, -1));
  };

  const handleHint = () => {
    if (!solution || won) return;
    const h = getHint(board, solution);
    if (!h) return;
    setHistory(prev => [...prev, { board: board.map(r => [...r]), errors: { ...errors }, notes: { ...notes } }]);
    setHintCount(hc => hc + 1);
    const nb = board.map(r => [...r]);
    nb[h.row][h.col] = h.value;
    setBoard(nb);
    setHinted(prev => ({ ...prev, [`${h.row}-${h.col}`]: true }));
    setSelected([h.row, h.col]);
    setErrors(prev => { const e = { ...prev }; delete e[`${h.row}-${h.col}`]; return e; });
    setNotes(prev => { const n = { ...prev }; delete n[`${h.row}-${h.col}`]; return n; });
    const complete = nb.every((row, ri) => row.every((v, ci) => v !== 0 && v === solution[ri][ci]));
    if (complete) { setWon(true); setJustWon(true); setRunning(false); }
  };

  const isHighlighted = (r, c) => {
    if (!selected) return false;
    const [sr, sc] = selected;
    return r === sr || c === sc ||
      (Math.floor(r / 3) === Math.floor(sr / 3) && Math.floor(c / 3) === Math.floor(sc / 3));
  };

  const isSameVal = (r, c) => {
    if (!selected || !board) return false;
    const sv = board[selected[0]][selected[1]];
    return sv !== 0 && board[r][c] === sv;
  };

  const getNumberCount = (num) => board ? board.flat().filter(v => v === num).length : 0;

  if (!board) return (
    <div className="loading">
      <div className="loading-spinner" />
      <span>Generating puzzle…</span>
    </div>
  );

  const filled = board.flat().filter(v => v !== 0).length;
  const pct = Math.round((filled / 81) * 100);
  const tip = TIPS[tipIdx % TIPS.length];

  return (
    <div className="app">
      {/* Animated background */}
      <div className="bg-canvas">
        <div className="orb orb1" />
        <div className="orb orb2" />
        <div className="orb orb3" />
        <div className="grid-lines" />
      </div>

      {/* Header */}
      <header className="header">
        <div className="logo">
          <span className="logo-symbol">✦</span>
          <span className="logo-text">SUDOKU</span>
        </div>
        <div className="header-stats">
          <div className="stat-chip">
            <span className="stat-icon">⏱</span>
            <span className="stat-val">{fmt(timer)}</span>
          </div>
          <div className="stat-chip">
            <span className="stat-icon">💡</span>
            <span className="stat-val">{hintCount}</span>
          </div>
        </div>
      </header>

      {/* Difficulty + New Game */}
      <div className="toolbar">
        <div className="diff-group">
          {Object.keys(DIFFICULTIES).map(d => (
            <button key={d}
              className={`diff-btn ${difficulty === d ? 'active' : ''}`}
              onClick={() => { setDifficulty(d); newGame(d); }}>
              {d}
            </button>
          ))}
        </div>
        <button className="new-btn" onClick={() => newGame()}>⟳ New Game</button>
      </div>

      {/* Main layout */}
      <div className="game-layout">

        {/* Board */}
        <div className="board-container">
          {justWon && (
            <div className="win-overlay">
              <div className="win-card">
                <div className="confetti-row">{['🎉','✨','🏆','✨','🎉'].map((e,i)=><span key={i} style={{animationDelay:`${i*0.1}s`}}>{e}</span>)}</div>
                <h2 className="win-title">Brilliant!</h2>
                <p className="win-details">Solved in <strong>{fmt(timer)}</strong> · <strong>{hintCount}</strong> hint{hintCount !== 1 ? 's' : ''}</p>
                <div className="win-rating">
                  {hintCount === 0 ? '⭐⭐⭐ Perfect!' : hintCount <= 2 ? '⭐⭐ Great!' : '⭐ Good job!'}
                </div>
                <button className="new-btn" onClick={() => newGame()}>Play Again</button>
              </div>
            </div>
          )}

          <div className="board">
            {board.map((row, r) => row.map((val, c) => {
              const key = `${r}-${c}`;
              const isLock = locked[key];
              const isSel = selected && selected[0] === r && selected[1] === c;
              const isErr = errors[key];
              const isHint = hinted[key];
              const isShake = shake === key;
              const cellNotes = notes[key];
              const classes = [
                'cell',
                isLock ? 'locked' : 'editable',
                isSel ? 'selected' : '',
                !isSel && isHighlighted(r, c) ? 'highlighted' : '',
                !isSel && isSameVal(r, c) ? 'same-val' : '',
                isErr ? 'error' : '',
                isHint ? 'hinted' : '',
                isShake ? 'shake' : '',
                c === 2 ? 'bb-right' : '',
                c === 5 ? 'bb-right' : '',
                r === 2 ? 'bb-bottom' : '',
                r === 5 ? 'bb-bottom' : '',
              ].filter(Boolean).join(' ');

              return (
                <div key={key} className={classes} onClick={() => handleCell(r, c)}>
                  {val !== 0 ? (
                    <span className="cell-val">{val}</span>
                  ) : cellNotes && cellNotes.size > 0 ? (
                    <div className="notes-grid">
                      {[1,2,3,4,5,6,7,8,9].map(n => (
                        <span key={n} className={`note ${cellNotes.has(n) ? 'on' : ''}`}>{n}</span>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            }))}
          </div>
        </div>

        {/* Side panel */}
        <div className="side">

          {/* Number pad */}
          <div className="numpad-section">
            <div className="section-label">Numbers</div>
            <div className="numpad">
              {[1,2,3,4,5,6,7,8,9].map(n => {
                const count = getNumberCount(n);
                return (
                  <button key={n}
                    className={`nkey ${count >= 9 ? 'done' : ''}`}
                    onClick={() => handleInput(n)}
                    disabled={count >= 9}>
                    <span className="nkey-num">{n}</span>
                    <span className="nkey-count">{count}/9</span>
                  </button>
                );
              })}
              <button className="nkey erase-key" onClick={() => handleInput(0)}>⌫</button>
            </div>
          </div>

          {/* Actions */}
          <div className="actions">
            <button className={`action-btn ${noteMode ? 'active-note' : ''}`} onClick={() => setNoteMode(m => !m)}>
              <span>✏️</span><span>{noteMode ? 'Notes: ON' : 'Notes'}</span>
            </button>
            <button className="action-btn" onClick={handleUndo} disabled={!history.length}>
              <span>↩</span><span>Undo</span>
            </button>
            <button className="action-btn hint-action" onClick={handleHint}>
              <span>💡</span><span>Hint</span>
            </button>
          </div>

          {/* Progress */}
          <div className="progress-card">
            <div className="progress-header">
              <span>Progress</span>
              <span className="progress-pct">{pct}%</span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${pct}%` }} />
            </div>
            <div className="progress-counts">
              <span>{filled} filled</span>
              <span>{81 - filled} left</span>
            </div>
          </div>

          {/* Tip card */}
          <div className="tip-card">
            <div className="tip-badge">💬 Strategy Tip</div>
            <div className="tip-title">{tip.title}</div>
            <div className="tip-body">{tip.body}</div>
            <button className="tip-next" onClick={() => setTipIdx(i => (i + 1) % TIPS.length)}>Next tip →</button>
          </div>

        </div>
      </div>
    </div>
  );
}
