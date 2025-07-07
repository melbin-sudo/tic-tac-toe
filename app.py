from flask import Flask, request, render_template_string
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging
import os
import uuid
import time
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Fix for deployment issues - Updated configuration
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    logger=False,
    engineio_logger=False,
    async_mode='threading',
    transports=['websocket', 'polling'],
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1000000
)

# Store game rooms and players
game_rooms = {}
players = {}
waiting_players = []

class GameRoom:
    def __init__(self, room_id):
        self.room_id = room_id
        self.players = {}  # player_id -> player_info
        self.game_state = {
            'board': [None] * 9,
            'current_player': None,
            'game_active': False,
            'winner': None,
            'moves': 0
        }
        self.created_at = time.time()
        self.last_activity = time.time()
    
    def add_player(self, player_id, player_info):
        if len(self.players) < 2:
            self.players[player_id] = player_info
            self.last_activity = time.time()
            return True
        return False
    
    def remove_player(self, player_id):
        if player_id in self.players:
            del self.players[player_id]
            self.last_activity = time.time()
    
    def is_full(self):
        return len(self.players) >= 2
    
    def is_empty(self):
        return len(self.players) == 0
    
    def get_player_list(self):
        return list(self.players.keys())
    
    def start_game(self):
        if len(self.players) == 2:
            self.game_state['game_active'] = True
            player_ids = list(self.players.keys())
            self.game_state['current_player'] = player_ids[0]  # First player goes first
            self.last_activity = time.time()
            return True
        return False

# HTML template with lobby system
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Player WebRTC Tic-Tac-Toe</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.2);
            max-width: 800px;
            width: 100%;
        }
        
        h1 {
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
        }
        
        .lobby-section {
            margin-bottom: 30px;
            text-align: center;
        }
        
        .player-info {
            background: rgba(255, 255, 255, 0.1);
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        
        .player-name-input {
            padding: 10px;
            border: none;
            border-radius: 5px;
            font-size: 1em;
            margin-right: 10px;
            background: rgba(255, 255, 255, 0.9);
            color: #333;
        }
        
        .room-controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .room-list {
            background: rgba(255, 255, 255, 0.1);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: left;
        }
        
        .room-item {
            background: rgba(255, 255, 255, 0.1);
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .room-item.full {
            opacity: 0.6;
        }
        
        .room-info {
            flex: 1;
        }
        
        .room-name {
            font-weight: bold;
            font-size: 1.1em;
            margin-bottom: 5px;
        }
        
        .room-players {
            font-size: 0.9em;
            opacity: 0.8;
        }
        
        .game-section {
            display: none;
        }
        
        .game-section.active {
            display: block;
        }
        
        .game-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .game-info {
            text-align: center;
            margin-bottom: 20px;
        }
        
        .status {
            font-weight: bold;
            font-size: 1.2em;
            margin: 10px 0;
        }
        
        .board {
            display: grid;
            grid-template-columns: repeat(3, 100px);
            grid-template-rows: repeat(3, 100px);
            gap: 5px;
            margin: 20px auto;
            background: rgba(255, 255, 255, 0.2);
            padding: 10px;
            border-radius: 15px;
            justify-content: center;
        }
        
        .cell {
            background: rgba(255, 255, 255, 0.9);
            border: none;
            border-radius: 10px;
            font-size: 2em;
            font-weight: bold;
            color: #333;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        }
        
        .cell:hover {
            background: rgba(255, 255, 255, 1);
            transform: scale(1.05);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
        }
        
        .cell.disabled {
            cursor: not-allowed;
            opacity: 0.7;
        }
        
        .player-display {
            display: flex;
            justify-content: space-between;
            margin-bottom: 20px;
        }
        
        .player {
            padding: 15px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            flex: 1;
            margin: 0 5px;
            text-align: center;
        }
        
        .player.active {
            background: rgba(255, 255, 255, 0.2);
            box-shadow: 0 0 10px rgba(255, 255, 255, 0.5);
        }
        
        .player.winner {
            background: rgba(255, 193, 7, 0.3);
            box-shadow: 0 0 15px rgba(255, 193, 7, 0.5);
        }
        
        button {
            background: linear-gradient(45deg, #ff6b6b, #feca57);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            font-size: 1em;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            margin: 5px;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
        }
        
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .btn-secondary {
            background: linear-gradient(45deg, #5f6368, #9aa0a6);
        }
        
        .btn-success {
            background: linear-gradient(45deg, #2ed573, #1e90ff);
        }
        
        .btn-danger {
            background: linear-gradient(45deg, #ff4757, #ff6b6b);
        }
        
        .connection-info {
            text-align: center;
            margin-bottom: 20px;
            padding: 10px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            font-size: 0.9em;
        }
        
        .stats {
            display: flex;
            justify-content: space-around;
            margin-bottom: 20px;
            text-align: center;
        }
        
        .stat {
            background: rgba(255, 255, 255, 0.1);
            padding: 10px;
            border-radius: 8px;
            flex: 1;
            margin: 0 5px;
        }
        
        .winner-announcement {
            font-size: 1.5em;
            font-weight: bold;
            color: #feca57;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
            margin: 20px 0;
            text-align: center;
        }
        
        .debug {
            background: rgba(255, 255, 255, 0.1);
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            font-size: 0.8em;
            max-height: 200px;
            overflow-y: auto;
        }
        
        .debug-header {
            font-weight: bold;
            margin-bottom: 10px;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 20px;
                margin: 10px;
            }
            
            h1 {
                font-size: 2em;
            }
            
            .board {
                grid-template-columns: repeat(3, 80px);
                grid-template-rows: repeat(3, 80px);
            }
            
            .cell {
                font-size: 1.5em;
            }
            
            .room-controls {
                flex-direction: column;
                align-items: center;
            }
            
            .room-item {
                flex-direction: column;
                align-items: stretch;
                text-align: center;
            }
            
            .player-display {
                flex-direction: column;
            }
            
            .player {
                margin: 5px 0;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 Multi-Player Tic-Tac-Toe</h1>
        
        <div class="connection-info">
            <div>Connection: <span id="connection-status">Connecting...</span></div>
            <div>Player: <span id="player-name-display">-</span></div>
        </div>
        
        <div class="stats">
            <div class="stat">
                <div>Active Games</div>
                <div id="active-games">0</div>
            </div>
            <div class="stat">
                <div>Online Players</div>
                <div id="online-players">0</div>
            </div>
            <div class="stat">
                <div>Waiting Players</div>
                <div id="waiting-players">0</div>
            </div>
        </div>
        
        <!-- Lobby Section -->
        <div class="lobby-section" id="lobby-section">
            <div class="player-info">
                <input type="text" id="player-name" class="player-name-input" placeholder="Enter your name" maxlength="20">
                <button onclick="setPlayerName()" id="set-name-btn">Set Name</button>
            </div>
            
            <div class="room-controls">
                <button onclick="createRoom()" id="create-room-btn" disabled>Create Room</button>
                <button onclick="joinRandomRoom()" id="join-random-btn" disabled>Quick Match</button>
                <button onclick="refreshRooms()" id="refresh-rooms-btn">Refresh Rooms</button>
            </div>
            
            <div class="room-list">
                <div class="room-list-header">
                    <h3>Available Rooms</h3>
                </div>
                <div id="room-list-content">
                    <div style="text-align: center; opacity: 0.7;">Loading rooms...</div>
                </div>
            </div>
        </div>
        
        <!-- Game Section -->
        <div class="game-section" id="game-section">
            <div class="game-header">
                <h3>Room: <span id="current-room-name">-</span></h3>
                <button onclick="leaveRoom()" class="btn-secondary">Leave Room</button>
            </div>
            
            <div class="player-display">
                <div class="player" id="player1">
                    <div class="player-name">Player 1</div>
                    <div class="player-symbol">X</div>
                </div>
                <div class="player" id="player2">
                    <div class="player-name">Player 2</div>
                    <div class="player-symbol">O</div>
                </div>
            </div>
            
            <div class="game-info">
                <div class="status" id="game-status">Waiting for players...</div>
            </div>
            
            <div class="board" id="board"></div>
            
            <div class="room-controls">
                <button onclick="startGame()" id="start-game-btn" disabled>Start Game</button>
                <button onclick="resetGame()" id="reset-game-btn">Reset Game</button>
            </div>
        </div>
        
        <div class="debug" id="debug">
            <div class="debug-header">Debug Log:</div>
            <div id="debug-log"></div>
        </div>
    </div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.0/socket.io.js"></script>
    <script>
        // Initialize socket connection
        const socket = io({
            transports: ['websocket', 'polling'],
            upgrade: false,
            rememberUpgrade: false,
            timeout: 30000,
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 2000
        });
        
        // DOM elements
        const lobbySection = document.getElementById('lobby-section');
        const gameSection = document.getElementById('game-section');
        const playerNameInput = document.getElementById('player-name');
        const playerNameDisplay = document.getElementById('player-name-display');
        const connectionStatus = document.getElementById('connection-status');
        const roomListContent = document.getElementById('room-list-content');
        const currentRoomName = document.getElementById('current-room-name');
        const gameStatus = document.getElementById('game-status');
        const board = document.getElementById('board');
        const debugLog = document.getElementById('debug-log');
        const activeGamesSpan = document.getElementById('active-games');
        const onlinePlayersSpan = document.getElementById('online-players');
        const waitingPlayersSpan = document.getElementById('waiting-players');
        
        // Game state
        let playerName = '';
        let playerId = '';
        let currentRoom = null;
        let gameBoard = Array(9).fill(null);
        let isMyTurn = false;
        let gameActive = false;
        let mySymbol = '';
        let opponentSymbol = '';
        let peerConnection = null;
        let dataChannel = null;
        let cells = [];
        
        // Generate unique player ID
        playerId = 'player_' + Math.random().toString(36).substring(2, 10);
        
        // Debug logging
        function log(message) {
            console.log(message);
            const timestamp = new Date().toLocaleTimeString();
            debugLog.innerHTML += `<div>${timestamp}: ${message}</div>`;
            debugLog.scrollTop = debugLog.scrollHeight;
        }
        
        // Initialize game board
        function initializeBoard() {
            board.innerHTML = '';
            cells = [];
            gameBoard = Array(9).fill(null);
            
            for (let i = 0; i < 9; i++) {
                const cell = document.createElement('div');
                cell.classList.add('cell');
                cell.dataset.index = i;
                cell.addEventListener('click', () => makeMove(i));
                board.appendChild(cell);
                cells.push(cell);
            }
        }
        
        // Set player name
        function setPlayerName() {
            const name = playerNameInput.value.trim();
            if (name.length < 2) {
                alert('Please enter a name with at least 2 characters');
                return;
            }
            
            playerName = name;
            playerNameDisplay.textContent = playerName;
            playerNameInput.disabled = true;
            document.getElementById('set-name-btn').disabled = true;
            document.getElementById('create-room-btn').disabled = false;
            document.getElementById('join-random-btn').disabled = false;
            
            // Register player with server
            socket.emit('register_player', { 
                player_id: playerId, 
                player_name: playerName 
            });
            
            log(`Player name set to: ${playerName}`);
        }
        
        // Create new room
        function createRoom() {
            if (!playerName) {
                alert('Please set your name first');
                return;
            }
            
            const roomName = `${playerName}'s Room`;
            socket.emit('create_room', { 
                player_id: playerId, 
                room_name: roomName 
            });
            
            log(`Creating room: ${roomName}`);
        }
        
        // Join specific room
        function joinRoom(roomId) {
            if (!playerName) {
                alert('Please set your name first');
                return;
            }
            
            socket.emit('join_room', { 
                player_id: playerId, 
                room_id: roomId 
            });
            
            log(`Joining room: ${roomId}`);
        }
        
        // Join random available room
        function joinRandomRoom() {
            if (!playerName) {
                alert('Please set your name first');
                return;
            }
            
            socket.emit('join_random_room', { 
                player_id: playerId 
            });
            
            log('Looking for random room...');
        }
        
        // Refresh room list
        function refreshRooms() {
            socket.emit('get_rooms');
            log('Refreshing room list...');
        }
        
        // Leave current room
        function leaveRoom() {
            if (currentRoom) {
                socket.emit('leave_room', { 
                    player_id: playerId, 
                    room_id: currentRoom 
                });
                
                // Close WebRTC connection
                if (peerConnection) {
                    peerConnection.close();
                    peerConnection = null;
                }
                if (dataChannel) {
                    dataChannel.close();
                    dataChannel = null;
                }
                
                currentRoom = null;
                gameActive = false;
                showLobby();
                log('Left room');
            }
        }
        
        // Start game
        function startGame() {
            if (currentRoom) {
                socket.emit('start_game', { 
                    player_id: playerId, 
                    room_id: currentRoom 
                });
                log('Starting game...');
            }
        }
        
        // Reset game
        function resetGame() {
            if (currentRoom) {
                socket.emit('reset_game', {
                    player_id: playerId,
                    room_id: currentRoom
                });
            }
        }
        
        // Make a move
        function makeMove(index) {
            if (!gameActive || !isMyTurn || gameBoard[index]) {
                return;
            }
            
            // Send move to server for validation and tracking
            socket.emit('make_move', {
                player_id: playerId,
                room_id: currentRoom,
                index: index
            });
        }
        
        // Handle opponent's move
        function handleOpponentMove(index, symbol) {
            if (gameBoard[index] || !gameActive) return;
            
            gameBoard[index] = symbol;
            cells[index].textContent = symbol;
            cells[index].style.color = symbol === 'X' ? '#ff6b6b' : '#54a0ff';
            
            isMyTurn = true;
            checkWinner();
            updateGameStatus();
        }
        
        // Check for winner
        function checkWinner() {
            const winPatterns = [
                [0, 1, 2], [3, 4, 5], [6, 7, 8], // rows
                [0, 3, 6], [1, 4, 7], [2, 5, 8], // columns
                [0, 4, 8], [2, 4, 6] // diagonals
            ];
            
            for (const pattern of winPatterns) {
                const [a, b, c] = pattern;
                if (gameBoard[a] && gameBoard[a] === gameBoard[b] && gameBoard[a] === gameBoard[c]) {
                    const winner = gameBoard[a];
                    endGame(winner === mySymbol ? 'You win!' : 'Opponent wins!', winner);
                    return;
                }
            }
            
            if (gameBoard.every(cell => cell !== null)) {
                endGame("It's a tie!", null);
            }
        }
        
        // End game
        function endGame(message, winner) {
            gameActive = false;
            gameStatus.innerHTML = `<div class="winner-announcement">${message}</div>`;
            
            // Highlight winner
            const player1 = document.getElementById('player1');
            const player2 = document.getElementById('player2');
            player1.classList.remove('active', 'winner');
            player2.classList.remove('active', 'winner');
            
            if (winner) {
                if (winner === mySymbol) {
                    player1.classList.add('winner');
                } else {
                    player2.classList.add('winner');
                }
            }
            
            // Disable cells
            cells.forEach(cell => cell.classList.add('disabled'));
            
            log(`Game ended: ${message}`);
        }
        
        // Update game status
        function updateGameStatus(customMessage = null) {
            if (customMessage) {
                gameStatus.textContent = customMessage;
                return;
            }
            
            if (!gameActive) {
                gameStatus.textContent = 'Game not started';
                document.getElementById('player1').classList.remove('active');
                document.getElementById('player2').classList.remove('active');
            } else if (isMyTurn) {
                gameStatus.textContent = 'Your turn';
                document.getElementById('player1').classList.add('active');
                document.getElementById('player2').classList.remove('active');
            } else {
                gameStatus.textContent = "Opponent's turn";
                document.getElementById('player1').classList.remove('active');
                document.getElementById('player2').classList.add('active');
            }
        }
        
        // Show lobby
        function showLobby() {
            lobbySection.style.display = 'block';
            gameSection.classList.remove('active');
            refreshRooms();
        }
        
        // Show game
        function showGame() {
            lobbySection.style.display = 'none';
            gameSection.classList.add('active');
        }
        
        // Create WebRTC peer connection
        function createPeerConnection() {
            peerConnection = new RTCPeerConnection({
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' },
                    { urls: 'stun:stun1.l.google.com:19302' }
                ]
            });
            
            peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    socket.emit('webrtc_candidate', {
                        player_id: playerId,
                        room_id: currentRoom,
                        candidate: event.candidate
                    });
                }
            };
            
            peerConnection.ondatachannel = (event) => {
                setupDataChannel(event.channel);
            };
            
            peerConnection.onconnectionstatechange = () => {
                log(`WebRTC connection state: ${peerConnection.connectionState}`);
            };
        }
        
        // Setup data channel
        function setupDataChannel(channel) {
            dataChannel = channel;
            
            dataChannel.onopen = () => {
                log('Data channel opened');
                updateGameStatus('Connection established');
            };
            
            dataChannel.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'move') {
                    handleOpponentMove(data.index, data.symbol);
                } else if (data.type === 'reset') {
                    resetGame();
                }
            };
            
            dataChannel.onclose = () => {
                log('Data channel closed');
                updateGameStatus('Connection lost');
            };
        }
        
        // Socket event handlers
        socket.on('connect', () => {
            log('Connected to server');
            connectionStatus.textContent = 'Connected';
            connectionStatus.style.color = '#2ed573';
        });
        
        socket.on('disconnect', () => {
            log('Disconnected from server');
            connectionStatus.textContent = 'Disconnected';
            connectionStatus.style.color = '#ff6b6b';
        });
        
        socket.on('room_created', (data) => {
            log(`Room created: ${data.room_id}`);
            currentRoom = data.room_id;
            currentRoomName.textContent = data.room_name;
            showGame();
            initializeBoard();
        });
        
        socket.on('room_joined', (data) => {
            log(`Joined room: ${data.room_id}`);
            currentRoom = data.room_id;
            currentRoomName.textContent = data.room_name;
            showGame();
            initializeBoard();
            
            // Update player displays
            const players = data.players;
            if (players.length >= 1) {
                document.querySelector('#player1 .player-name').textContent = players[0].name;
            }
            if (players.length >= 2) {
                document.querySelector('#player2 .player-name').textContent = players[1].name;
                // Enable start game button when 2 players are present
                document.getElementById('start-game-btn').disabled = false;
            } else {
                // Disable start game button if less than 2 players
                document.getElementById('start-game-btn').disabled = true;
            }
            
            // Update game status based on player count
            if (players.length < 2) {
                updateGameStatus('Waiting for another player...');
            } else {
                updateGameStatus('Ready to start game!');
            }
        });
        
        socket.on('room_left', () => {
            log('Left room');
            currentRoom = null;
            showLobby();
        });
        
        socket.on('game_started', (data) => {
            log(`Game started. You are: ${data.symbol}`);
            gameActive = true;
            mySymbol = data.symbol;
            opponentSymbol = data.symbol === 'X' ? 'O' : 'X';
            isMyTurn = data.your_turn;
            updateGameStatus();
            
            document.getElementById('start-game-btn').disabled = true;
            
            // Setup WebRTC if you're the host
            if (data.is_host) {
                createPeerConnection();
                dataChannel = peerConnection.createDataChannel('game');
                setupDataChannel(dataChannel);
                
                peerConnection.createOffer().then(offer => {
                    return peerConnection.setLocalDescription(offer);
                }).then(() => {
                    socket.emit('webrtc_offer', {
                        player_id: playerId,
                        room_id: currentRoom,
                        offer: peerConnection.localDescription
                    });
                });
            }
        });
        
        socket.on('move_made', (data) => {
            const { player_id, index, symbol, board, current_player, winner, game_active, moves } = data;
            
            // Update local game state
            gameBoard = board;
            gameActive = game_active;
            
            // Update board display
            cells[index].textContent = symbol;
            cells[index].style.color = symbol === 'X' ? '#ff6b6b' : '#54a0ff';
            
            // Update turn
            isMyTurn = (current_player === playerId);
            
            // Check for game end
            if (winner) {
                if (winner === 'tie') {
                    endGame("It's a tie!", null);
                } else {
                    const isWinner = (winner === mySymbol);
                    endGame(isWinner ? 'You win!' : 'Opponent wins!', winner);
                }
            } else {
                updateGameStatus();
            }
            
            // Also send move through WebRTC for backup/redundancy
            if (player_id === playerId && dataChannel && dataChannel.readyState === 'open') {
                dataChannel.send(JSON.stringify({
                    type: 'move',
                    index: index,
                    symbol: symbol
                }));
            }
        });

        socket.on('game_reset', (data) => {
            gameBoard = Array(9).fill(null);
            gameActive = false;
            isMyTurn = false;
            initializeBoard();
            updateGameStatus('Game reset');
            
            // Also send reset through WebRTC
            if (dataChannel && dataChannel.readyState === 'open') {
                dataChannel.send(JSON.stringify({
                    type: 'reset'
                }));
            }
        });

        socket.on('rooms_list', (data) => {
            log(`Received ${data.rooms.length} rooms`);
            displayRooms(data.rooms);
        });
        
        socket.on('stats_update', (data) => {
            activeGamesSpan.textContent = data.active_games;
            onlinePlayersSpan.textContent = data.online_players;
            waitingPlayersSpan.textContent = data.waiting_players;
        });
        
        socket.on('webrtc_offer', async (data) => {
            log('Received WebRTC offer');
            createPeerConnection();
            
            await peerConnection.setRemoteDescription(data.offer);
            const answer = await peerConnection.createAnswer();
            await peerConnection.setLocalDescription(answer);
            
            socket.emit('webrtc_answer', {
                player_id: playerId,
                room_id: currentRoom,
                answer: peerConnection.localDescription
            });
        });
        
        socket.on('webrtc_answer', async (data) => {
            log('Received WebRTC answer');
            await peerConnection.setRemoteDescription(data.answer);
        });
        
        socket.on('webrtc_candidate', async (data) => {
            log('Received WebRTC candidate');
            if (peerConnection) {
                await peerConnection.addIceCandidate(data.candidate);
            }
        });
        
        socket.on('error', (data) => {
            log(`Error: ${data.message}`);
            alert(`Error: ${data.message}`);
        });
        
        // Display rooms in lobby
        function displayRooms(rooms) {
            if (rooms.length === 0) {
                roomListContent.innerHTML = '<div style="text-align: center; opacity: 0.7;">No rooms available</div>';
                return;
            }
            
            roomListContent.innerHTML = '';
            rooms.forEach(room => {
                const roomDiv = document.createElement('div');
                roomDiv.className = `room-item ${room.is_full ? 'full' : ''}`;
                
                roomDiv.innerHTML = `
                    <div class="room-info">
                        <div class="room-name">${room.name}</div>
                        <div class="room-players">Players: ${room.player_count}/2</div>
                    </div>
                    <button onclick="joinRoom('${room.id}')" 
                            ${room.is_full ? 'disabled' : ''} 
                            class="btn-success">
                        ${room.is_full ? 'Full' : 'Join'}
                    </button>
                `;
                
                roomListContent.appendChild(roomDiv);
            });
        }
        
        // Initialize
        initializeBoard();
        showLobby();
        refreshRooms();
        log('Game initialized');
        
        // Auto-refresh rooms every 10 seconds
        setInterval(refreshRooms, 10000);
    </script>
</body>
</html>
'''

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/status")
def status():
    return {
        "status": "running",
        "rooms": len(game_rooms),
        "players": len(players),
        "waiting_players": len(waiting_players)
    }

@app.route("/health")
def health():
    return {"status": "healthy"}

@socketio.on("connect")
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    emit("connected", {"sid": request.sid})

@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")
    
    # Find and remove player
    player_id = None
    for pid, player_info in players.items():
        if player_info.get('sid') == request.sid:
            player_id = pid
            break
    
    if player_id:
        # Remove from waiting list
        waiting_players[:] = [p for p in waiting_players if p != player_id]
        
        # Remove from any room
        for room_id, room in list(game_rooms.items()):
            if player_id in room.players:
                room.remove_player(player_id)
                emit("player_left", {"player_id": player_id}, room=room_id)
                
                # Remove empty rooms
                if room.is_empty():
                    del game_rooms[room_id]
                    logger.info(f"Removed empty room: {room_id}")
                break
        
        # Remove player
        del players[player_id]
        logger.info(f"Player {player_id} disconnected")
    
    broadcast_stats()

@socketio.on("register_player")
def handle_register_player(data):
    player_id = data["player_id"]
    player_name = data["player_name"]
    
    players[player_id] = {
        "name": player_name,
        "sid": request.sid,
        "connected_at": datetime.now().isoformat()
    }
    
    logger.info(f"Player registered: {player_id} ({player_name})")
    emit("player_registered", {"player_id": player_id})
    broadcast_stats()

@socketio.on("create_room")
def handle_create_room(data):
    player_id = data["player_id"]
    room_name = data["room_name"]
    
    if player_id not in players:
        emit("error", {"message": "Player not registered"})
        return
    
    room_id = str(uuid.uuid4())[:8]
    room = GameRoom(room_id)
    
    player_info = players[player_id]
    room.add_player(player_id, player_info)
    game_rooms[room_id] = room
    
    # Join socket room
    join_room(room_id)
    
    # Remove from waiting list
    if player_id in waiting_players:
        waiting_players.remove(player_id)
    
    emit("room_created", {
        "room_id": room_id,
        "room_name": room_name,
        "players": [{"id": player_id, "name": player_info["name"]}]
    })
    
    logger.info(f"Room created: {room_id} by {player_id}")
    broadcast_stats()

@socketio.on("join_room")
def handle_join_room(data):
    player_id = data["player_id"]
    room_id = data["room_id"]
    
    if player_id not in players:
        emit("error", {"message": "Player not registered"})
        return
    
    if room_id not in game_rooms:
        emit("error", {"message": "Room not found"})
        return
    
    room = game_rooms[room_id]
    
    if room.is_full():
        emit("error", {"message": "Room is full"})
        return
    
    player_info = players[player_id]
    room.add_player(player_id, player_info)
    
    # Join socket room
    join_room(room_id)
    
    # Remove from waiting list
    if player_id in waiting_players:
        waiting_players.remove(player_id)
    
    # Get room name from first player
    room_name = f"Room {room_id}"
    
    # Prepare players list
    players_list = []
    for pid, pinfo in room.players.items():
        players_list.append({"id": pid, "name": pinfo["name"]})
    
    emit("room_joined", {
        "room_id": room_id,
        "room_name": room_name,
        "players": players_list
    })
    
    # Notify other players in room
    emit("player_joined", {
        "player_id": player_id,
        "player_name": player_info["name"],
        "players": players_list
    }, room=room_id, include_self=False)
    
    # Check if room is now full and auto-start game
    if room.is_full():
        logger.info(f"Room {room_id} is full, auto-starting game")
        # Auto-start the game when room is full
        if room.start_game():
            player_list = room.get_player_list()
            
            # Assign symbols and turns
            for i, pid in enumerate(player_list):
                symbol = 'X' if i == 0 else 'O'
                your_turn = (i == 0)  # First player goes first
                is_host = (i == 0)    # First player is host for WebRTC
                
                emit("game_started", {
                    "room_id": room_id,
                    "symbol": symbol,
                    "your_turn": your_turn,
                    "is_host": is_host
                }, room=players[pid]["sid"])
            
            logger.info(f"Game auto-started in room {room_id}")
    
    logger.info(f"Player {player_id} joined room {room_id}")
    broadcast_stats()

@socketio.on("join_random_room")
def handle_join_random_room(data):
    player_id = data["player_id"]
    
    if player_id not in players:
        emit("error", {"message": "Player not registered"})
        return
    
    # Find available room
    available_room = None
    for room_id, room in game_rooms.items():
        if not room.is_full():
            available_room = room
            break
    
    if available_room:
        # Join existing room
        handle_join_room({"player_id": player_id, "room_id": available_room.room_id})
    else:
        # Create new room
        room_name = f"{players[player_id]['name']}'s Room"
        handle_create_room({"player_id": player_id, "room_name": room_name})

@socketio.on("leave_room")
def handle_leave_room(data):
    player_id = data["player_id"]
    room_id = data["room_id"]
    
    if room_id not in game_rooms:
        return
    
    room = game_rooms[room_id]
    room.remove_player(player_id)
    
    # Leave socket room
    leave_room(room_id)
    
    # Notify other players
    emit("player_left", {"player_id": player_id}, room=room_id)
    
    # Remove empty rooms
    if room.is_empty():
        del game_rooms[room_id]
        logger.info(f"Removed empty room: {room_id}")
    
    emit("room_left", {"room_id": room_id})
    logger.info(f"Player {player_id} left room {room_id}")
    broadcast_stats()

@socketio.on("start_game")
def handle_start_game(data):
    player_id = data["player_id"]
    room_id = data["room_id"]
    
    if room_id not in game_rooms:
        emit("error", {"message": "Room not found"})
        return
    
    room = game_rooms[room_id]
    
    if not room.is_full():
        emit("error", {"message": "Need 2 players to start game"})
        return
    
    # Check if game is already started
    if room.game_state["game_active"]:
        emit("error", {"message": "Game already in progress"})
        return
    
    if room.start_game():
        player_list = room.get_player_list()
        
        # Assign symbols and turns
        for i, pid in enumerate(player_list):
            symbol = 'X' if i == 0 else 'O'
            your_turn = (i == 0)  # First player goes first
            is_host = (i == 0)    # First player is host for WebRTC
            
            emit("game_started", {
                "room_id": room_id,
                "symbol": symbol,
                "your_turn": your_turn,
                "is_host": is_host
            }, room=players[pid]["sid"])
        
        logger.info(f"Game manually started in room {room_id}")
        broadcast_stats()

@socketio.on("get_rooms")
def handle_get_rooms(data=None):
    rooms_list = []
    for room_id, room in game_rooms.items():
        rooms_list.append({
            "id": room_id,
            "name": f"Room {room_id}",
            "player_count": len(room.players),
            "is_full": room.is_full(),
            "game_active": room.game_state["game_active"]
        })
    
    emit("rooms_list", {"rooms": rooms_list})

@socketio.on("make_move")
def handle_make_move(data):
    player_id = data["player_id"]
    room_id = data["room_id"]
    index = data["index"]
    
    if room_id not in game_rooms:
        emit("error", {"message": "Room not found"})
        return
    
    room = game_rooms[room_id]
    
    # Validate move
    if not room.game_state["game_active"]:
        emit("error", {"message": "Game not active"})
        return
    
    if room.game_state["current_player"] != player_id:
        emit("error", {"message": "Not your turn"})
        return
    
    if room.game_state["board"][index] is not None:
        emit("error", {"message": "Cell already occupied"})
        return
    
    # Make the move
    player_list = room.get_player_list()
    symbol = 'X' if player_list[0] == player_id else 'O'
    
    room.game_state["board"][index] = symbol
    room.game_state["moves"] += 1
    
    # Switch turns
    current_index = player_list.index(player_id)
    next_index = (current_index + 1) % 2
    room.game_state["current_player"] = player_list[next_index]
    
    # Check for winner
    winner = check_winner(room.game_state["board"])
    if winner:
        room.game_state["winner"] = winner
        room.game_state["game_active"] = False
        room.game_state["current_player"] = None
    elif room.game_state["moves"] >= 9:
        # It's a tie
        room.game_state["winner"] = "tie"
        room.game_state["game_active"] = False
        room.game_state["current_player"] = None
    
    # Broadcast move to all players in room
    emit("move_made", {
        "player_id": player_id,
        "index": index,
        "symbol": symbol,
        "board": room.game_state["board"],
        "current_player": room.game_state["current_player"],
        "winner": room.game_state["winner"],
        "game_active": room.game_state["game_active"],
        "moves": room.game_state["moves"]
    }, room=room_id)
    
    room.last_activity = time.time()
    logger.info(f"Move made in room {room_id}: player {player_id} at index {index}")
    broadcast_stats()

@socketio.on("reset_game")
def handle_reset_game(data):
    player_id = data["player_id"]
    room_id = data["room_id"]
    
    if room_id not in game_rooms:
        emit("error", {"message": "Room not found"})
        return
    
    room = game_rooms[room_id]
    
    # Reset game state
    room.game_state = {
        'board': [None] * 9,
        'current_player': None,
        'game_active': False,
        'winner': None,
        'moves': 0
    }
    
    # Broadcast reset to all players in room
    emit("game_reset", {
        "room_id": room_id,
        "board": room.game_state["board"],
        "game_active": room.game_state["game_active"]
    }, room=room_id)
    
    room.last_activity = time.time()
    logger.info(f"Game reset in room {room_id} by player {player_id}")
    broadcast_stats()

def check_winner(board):
    """Check if there's a winner on the board"""
    win_patterns = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],  # rows
        [0, 3, 6], [1, 4, 7], [2, 5, 8],  # columns
        [0, 4, 8], [2, 4, 6]  # diagonals
    ]
    
    for pattern in win_patterns:
        a, b, c = pattern
        if board[a] is not None and board[a] == board[b] == board[c]:
            return board[a]
    
    return None

@socketio.on("webrtc_offer")
def handle_webrtc_offer(data):
    player_id = data["player_id"]
    room_id = data["room_id"]
    offer = data["offer"]
    
    # Send offer to other player in room
    emit("webrtc_offer", {
        "player_id": player_id,
        "offer": offer
    }, room=room_id, include_self=False)

@socketio.on("webrtc_answer")
def handle_webrtc_answer(data):
    player_id = data["player_id"]
    room_id = data["room_id"]
    answer = data["answer"]
    
    # Send answer to other player in room
    emit("webrtc_answer", {
        "player_id": player_id,
        "answer": answer
    }, room=room_id, include_self=False)

@socketio.on("webrtc_candidate")
def handle_webrtc_candidate(data):
    player_id = data["player_id"]
    room_id = data["room_id"]
    candidate = data["candidate"]
    
    # Send candidate to other player in room
    emit("webrtc_candidate", {
        "player_id": player_id,
        "candidate": candidate
    }, room=room_id, include_self=False)

def broadcast_stats():
    """Broadcast server statistics to all clients"""
    active_games = sum(1 for room in game_rooms.values() if room.game_state["game_active"])
    
    socketio.emit("stats_update", {
        "active_games": active_games,
        "online_players": len(players),
        "waiting_players": len(waiting_players)
    })

def cleanup_old_rooms():
    """Clean up old inactive rooms"""
    current_time = time.time()
    rooms_to_remove = []
    
    for room_id, room in game_rooms.items():
        # Remove rooms inactive for more than 30 minutes
        if current_time - room.last_activity > 1800:  # 30 minutes
            rooms_to_remove.append(room_id)
    
    for room_id in rooms_to_remove:
        del game_rooms[room_id]
        logger.info(f"Cleaned up old room: {room_id}")

# Periodic cleanup
import threading
def periodic_cleanup():
    while True:
        time.sleep(600)  # Run every 10 minutes
        cleanup_old_rooms()

cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting multi-player signaling server on port {port}")
    print("For local access: http://localhost:5000")
    
    socketio.run(
        app, 
        host="0.0.0.0", 
        port=port, 
        debug=False, 
        allow_unsafe_werkzeug=True,
        use_reloader=False,
        log_output=False
    )
