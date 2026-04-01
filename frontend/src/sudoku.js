export function generateFullBoard() {
  const board = Array.from({ length: 9 }, () => Array(9).fill(0));
  fillBoard(board);
  return board;
}

function fillBoard(board) {
  const nums = [1,2,3,4,5,6,7,8,9];
  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      if (board[r][c] === 0) {
        const shuffled = [...nums].sort(() => Math.random() - 0.5);
        for (let n of shuffled) {
          if (isValid(board, r, c, n)) {
            board[r][c] = n;
            if (fillBoard(board)) return true;
            board[r][c] = 0;
          }
        }
        return false;
      }
    }
  }
  return true;
}

export function isValid(board, row, col, num) {
  for (let i = 0; i < 9; i++) {
    if (board[row][i] === num) return false;
    if (board[i][col] === num) return false;
  }
  const br = Math.floor(row / 3) * 3;
  const bc = Math.floor(col / 3) * 3;
  for (let r = br; r < br + 3; r++)
    for (let c = bc; c < bc + 3; c++)
      if (board[r][c] === num) return false;
  return true;
}

export function createPuzzle(full, clues = 35) {
  const puzzle = full.map(r => [...r]);
  let removed = 0;
  const cells = [];
  for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) cells.push([r, c]);
  cells.sort(() => Math.random() - 0.5);
  for (const [r, c] of cells) {
    if (removed >= 81 - clues) break;
    puzzle[r][c] = 0;
    removed++;
  }
  return puzzle;
}

export function getHint(puzzle, solution) {
  const empties = [];
  for (let r = 0; r < 9; r++)
    for (let c = 0; c < 9; c++)
      if (puzzle[r][c] === 0) empties.push([r, c]);
  if (empties.length === 0) return null;
  const [r, c] = empties[Math.floor(Math.random() * empties.length)];
  return { row: r, col: c, value: solution[r][c] };
}

export function getTip() {
  const tips = [
    'Look for rows, columns, or boxes with only one empty cell — the answer is forced!',
    'Scan each number 1–9. Find where it can only fit in one place in a row, column, or box.',
    'If a number can only go in two cells in a box, eliminate it from the rest of that row or column.',
    'Look for "naked pairs" — two cells in the same row/col/box with only the same two candidates.',
    'Start with the most constrained rows, columns, or boxes — those with the fewest empty cells.',
    'Use process of elimination: if 8 numbers are placed in a row, the 9th is forced.',
    'Focus on boxes first — they often give the clearest logical deductions.',
    'Try pencil-marking: note possible candidates in each empty cell, then eliminate.',
    'A number placed in a row AND column AND box can only go in one spot in that area.',
    'When stuck, count how many times each number appears — the rarest ones are easiest to place.'
  ];
  return tips[Math.floor(Math.random() * tips.length)];
}
