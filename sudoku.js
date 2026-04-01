export function generateFullBoard() {
  const board = Array.from({ length: 9 }, () => Array(9).fill(0));
  fillBoard(board);
  return board;
}

function fillBoard(board) {
  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      if (board[r][c] === 0) {
        const nums = [1,2,3,4,5,6,7,8,9].sort(() => Math.random() - 0.5);
        for (let n of nums) {
          if (isSafe(board, r, c, n)) {
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

function isSafe(board, row, col, num) {
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

export function isValid(board, row, col, num) {
  return isSafe(board, row, col, num);
}

export function createPuzzle(full, clues = 35) {
  const puzzle = full.map(r => [...r]);
  const cells = [];
  for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) cells.push([r, c]);
  cells.sort(() => Math.random() - 0.5);
  let removed = 0;
  for (const [r, c] of cells) {
    if (removed >= 81 - clues) break;
    puzzle[r][c] = 0;
    removed++;
  }
  return puzzle;
}

export function getHint(board, solution) {
  const empties = [];
  for (let r = 0; r < 9; r++)
    for (let c = 0; c < 9; c++)
      if (board[r][c] === 0) empties.push([r, c]);
  if (!empties.length) return null;
  const [r, c] = empties[Math.floor(Math.random() * empties.length)];
  return { row: r, col: c, value: solution[r][c] };
}

export const TIPS = [
  { title: 'Lone Singles', body: 'If a cell has only one possible number left, that must be the answer. Check every empty cell!' },
  { title: 'Hidden Singles', body: 'If a number can only go in one cell within a row, column, or box — place it there, even if that cell has other candidates.' },
  { title: 'Box Elimination', body: 'Once a number is placed in a box, remove it as a candidate from the rest of that box instantly.' },
  { title: 'Naked Pairs', body: 'If two cells in the same row/col/box share the same two candidates, eliminate those numbers from all other cells in that group.' },
  { title: 'Pointing Pairs', body: 'If a number in a box can only appear in one row or column, eliminate it from the rest of that row or column outside the box.' },
  { title: 'Scan Cross-hatch', body: 'Pick a number and scan rows + columns where it already appears — the remaining empty cells narrow down its placement.' },
  { title: 'Start Easy', body: 'Always solve what is forced first. Rows, columns, or boxes with 7+ filled cells have almost no choices left.' },
  { title: 'Use Notes', body: 'Enable Notes mode and pencil in all candidates. Then eliminate as you place numbers — patterns become obvious.' },
  { title: 'Work the Boxes', body: 'Boxes with more filled cells give you more constraints. Tackle them before open rows or columns.' },
  { title: 'Count Each Number', body: 'Find which numbers appear least often on the board. Those are easiest to complete since few spots are open.' }
];
