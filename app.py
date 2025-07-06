from flask import Flask, request, render_template_string
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Fix for Render deployment
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    logger=True, 
    engineio_logger=True,
    async_mode='threading',  # Important for Render
    transports=['websocket', 'polling']  # Allow fallback to polling
)

# Store connected clients
clients = {}

# HTML template as string - Updated with dynamic host detection
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WebRTC Tic-Tac-Toe</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 600px;
            margin: 50px auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
        }
        .game-info {
            text-align: center;
            margin-bottom: 20px;
            font-size: 1.1em;
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
        .controls {
            text-align: center;
            margin-top: 20px;
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
            margin: 0 10px;
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
        .connection-info {
            text-align: center;
            margin-bottom: 20px;
            padding: 10px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            font-size: 0.9em;
        }
        .player-info {
            display: flex;
            justify-content: space-between;
            margin-bottom: 20px;
        }
        .player {
            padding: 10px;
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
        .winner {
            font-size: 1.5em;
            font-weight: bold;
            color: #feca57;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
            margin: 20px 0;
        }
        .debug {
            background: rgba(255, 255, 255, 0.1);
            padding: 10px;
            border-radius: 10px;
            margin-top: 20px;
            font-size: 0.8em;
            text-align: left;
        }
        
        /* Mobile responsive styles */
        @media (max-width: 768px) {
            body {
                margin: 10px;
                padding: 10px;
            }
            .container {
                padding: 20px;
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
            button {
                padding: 10px 20px;
                font-size: 0.9em;
                margin: 5px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 WebRTC Tic-Tac-Toe</h1>
        
        <div class="connection-info">
            <div>Connection Status: <span id="connection-status">Connecting...</span></div>
            <div>Player ID: <span id="player-id">-</span></div>
        </div>
        <div class="player-info">
            <div class="player" id="player1">
                <div>You (X)</div>
                <div>🎯</div>
            </div>
            <div class="player" id="player2">
                <div>Opponent (O)</div>
                <div>🎯</div>
            </div>
        </div>
        <div class="game-info">
            <div class="status" id="game-status">Click 'Start Game' to host or 'Join Game' to wait for an invitation</div>
        </div>
        <div class="board" id="board"></div>
        <div class="controls">
            <button onclick="startGame()" id="start-btn">Start Game</button>
            <button onclick="resetGame()" id="reset-btn">Reset Game</button>
            <button onclick="joinGame()" id="join-btn">Join Game</button>
        </div>
        <div class="debug" id="debug">
            <div>Debug Log:</div>
            <div id="debug-log"></div>
        </div>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.0/socket.io.js"></script>
    <script>
        // Initialize socket connection with proper configuration for Render
        const socket = io({
            transports: ['websocket', 'polling'],
            upgrade: true,
            rememberUpgrade: true,
            timeout: 20000,
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000
        });
        
        const board = document.getElementById("board");
        const gameStatus = document.getElementById("game-status");
        const connectionStatus = document.getElementById("connection-status");
        const playerIdSpan = document.getElementById("player-id");
        const startBtn = document.getElementById("start-btn");
        const resetBtn = document.getElementById("reset-btn");
        const joinBtn = document.getElementById("join-btn");
        const player1 = document.getElementById("player1");
        const player2 = document.getElementById("player2");
        const debugLog = document.getElementById("debug-log");
        
        let cells = [];
        let isMyTurn = false;
        let gameActive = false;
        let dataChannel;
        let peerConnection;
        let isHost = false;
        let gameBoard = Array(9).fill(null);
        let pendingCandidates = [];
        
        const myId = Math.random().toString(36).substring(2, 8);
        
        // Debug logging
        function log(message) {
            console.log(message);
            debugLog.innerHTML += `<div>${new Date().toLocaleTimeString()}: ${message}</div>`;
            debugLog.scrollTop = debugLog.scrollHeight;
        }
        
        // Initialize the game board
        function initializeBoard() {
            board.innerHTML = '';
            cells = [];
            gameBoard = Array(9).fill(null);
            
            for (let i = 0; i < 9; i++) {
                const cell = document.createElement("div");
                cell.classList.add("cell");
                cell.dataset.index = i;
                cell.addEventListener("click", () => makeMove(i));
                board.appendChild(cell);
                cells.push(cell);
            }
        }
        
        // Make a move
        function makeMove(index) {
            if (!gameActive || !isMyTurn || gameBoard[index] || !dataChannel || dataChannel.readyState !== "open") {
                return;
            }
            
            gameBoard[index] = 'X';
            cells[index].textContent = 'X';
            cells[index].style.color = '#ff6b6b';
            
            // Send move to opponent
            dataChannel.send(JSON.stringify({
                type: 'move',
                index: index,
                symbol: 'X'
            }));
            
            isMyTurn = false;
            updateGameStatus();
            checkWinner();
        }
        
        // Handle opponent's move
        function handleOpponentMove(index) {
            if (gameBoard[index] || !gameActive) return;
            
            gameBoard[index] = 'O';
            cells[index].textContent = 'O';
            cells[index].style.color = '#54a0ff';
            
            isMyTurn = true;
            updateGameStatus();
            checkWinner();
        }
        
        // Update game status display
        function updateGameStatus() {
            if (!gameActive) {
                gameStatus.textContent = "Game not started";
                player1.classList.remove('active');
                player2.classList.remove('active');
            } else if (isMyTurn) {
                gameStatus.textContent = "Your turn";
                player1.classList.add('active');
                player2.classList.remove('active');
            } else {
                gameStatus.textContent = "Opponent's turn";
                player1.classList.remove('active');
                player2.classList.add('active');
            }
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
                    endGame(`${gameBoard[a] === 'X' ? 'You' : 'Opponent'} wins!`);
                    return;
                }
            }
            
            if (gameBoard.every(cell => cell !== null)) {
                endGame("It's a tie!");
            }
        }
        
        // End the game
        function endGame(message) {
            gameActive = false;
            gameStatus.innerHTML = `<div class="winner">${message}</div>`;
            player1.classList.remove('active');
            player2.classList.remove('active');
            
            // Disable all cells
            cells.forEach(cell => cell.classList.add('disabled'));
        }
        
        // Reset the game
        function resetGame() {
            gameActive = false;
            isMyTurn = false;
            initializeBoard();
            updateGameStatus();
            
            if (dataChannel && dataChannel.readyState === "open") {
                dataChannel.send(JSON.stringify({
                    type: 'reset'
                }));
            }
        }
        
        // Start the game (as host)
        function startGame() {
            log("Starting game as host");
            if (peerConnection) {
                peerConnection.close();
            }
            setupWebRTC();
        }
        
        // Join existing game
        function joinGame() {
            log("Ready to join game");
            if (peerConnection) {
                peerConnection.close();
            }
            
            // Reset state
            gameActive = false;
            isHost = false;
            pendingCandidates = [];
            
            // Create peer connection for joining
            createPeerConnection();
            
            gameStatus.textContent = "Waiting for game invitation...";
            startBtn.disabled = true;
            joinBtn.disabled = true;
        }
        
        // Create peer connection with more robust ICE servers
        function createPeerConnection() {
            log("Creating peer connection");
            peerConnection = new RTCPeerConnection({
                iceServers: [
                    { urls: "stun:stun.l.google.com:19302" },
                    { urls: "stun:stun1.l.google.com:19302" },
                    { urls: "stun:stun2.l.google.com:19302" },
                    { urls: "stun:stun3.l.google.com:19302" },
                    { urls: "stun:stun4.l.google.com:19302" }
                ],
                iceCandidatePoolSize: 10
            });
            
            peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    log("Sending ICE candidate");
                    socket.emit("candidate", { 
                        id: myId, 
                        candidate: event.candidate 
                    });
                } else {
                    log("All ICE candidates sent");
                }
            };
            
            peerConnection.ondatachannel = (event) => {
                log("Received data channel from peer");
                setupDataChannel(event.channel);
            };
            
            peerConnection.onconnectionstatechange = () => {
                log(`Connection state: ${peerConnection.connectionState}`);
                if (peerConnection.connectionState === 'connected') {
                    connectionStatus.textContent = "Connected to peer";
                    connectionStatus.style.color = '#2ed573';
                } else if (peerConnection.connectionState === 'disconnected') {
                    connectionStatus.textContent = "Disconnected from peer";
                    connectionStatus.style.color = '#ff6b6b';
                } else if (peerConnection.connectionState === 'connecting') {
                    connectionStatus.textContent = "Connecting to peer...";
                    connectionStatus.style.color = '#ffa502';
                } else if (peerConnection.connectionState === 'failed') {
                    connectionStatus.textContent = "Connection failed";
                    connectionStatus.style.color = '#ff6b6b';
                }
            };
            
            peerConnection.oniceconnectionstatechange = () => {
                log(`ICE connection state: ${peerConnection.iceConnectionState}`);
            };
            
            peerConnection.onicegatheringstatechange = () => {
                log(`ICE gathering state: ${peerConnection.iceGatheringState}`);
            };
        }
        
        // Setup WebRTC connection
        function setupWebRTC() {
            log("Setting up WebRTC connection");
            createPeerConnection();
            createOffer();
        }
        
        // Create WebRTC offer
        async function createOffer() {
            try {
                log("Creating data channel and offer");
                isHost = true;
                
                // Create data channel BEFORE creating offer
                dataChannel = peerConnection.createDataChannel("game", {
                    ordered: true
                });
                setupDataChannel(dataChannel);
                
                const offer = await peerConnection.createOffer();
                await peerConnection.setLocalDescription(offer);
                
                log("Sending offer to signaling server");
                socket.emit("offer", { id: myId, offer });
                
                gameStatus.textContent = "Waiting for opponent to join...";
                startBtn.disabled = true;
                joinBtn.disabled = true;
            } catch (error) {
                log(`Error creating offer: ${error.message}`);
                gameStatus.textContent = "Error creating game";
                startBtn.disabled = false;
                joinBtn.disabled = false;
            }
        }
        
        // Setup data channel
        function setupDataChannel(channel) {
            dataChannel = channel;
            log(`Setting up data channel. State: ${channel.readyState}`);
            
            dataChannel.onopen = () => {
                log("Data channel opened - game ready!");
                gameActive = true;
                isMyTurn = isHost; // Host goes first
                updateGameStatus();
                startBtn.disabled = true;
                joinBtn.disabled = true;
                connectionStatus.textContent = "Game ready!";
                connectionStatus.style.color = '#2ed573';
            };
            
            dataChannel.onclose = () => {
                log("Data channel closed");
                gameActive = false;
                updateGameStatus();
                startBtn.disabled = false;
                joinBtn.disabled = false;
                connectionStatus.textContent = "Game disconnected";
                connectionStatus.style.color = '#ff6b6b';
            };
            
            dataChannel.onerror = (error) => {
                log(`Data channel error: ${error.error || error}`);
            };
            
            dataChannel.onmessage = (event) => {
                log(`Received message: ${event.data}`);
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'move') {
                        handleOpponentMove(data.index);
                    } else if (data.type === 'reset') {
                        gameActive = false;
                        isMyTurn = false;
                        initializeBoard();
                        updateGameStatus();
                    }
                } catch (error) {
                    log(`Error parsing message: ${error.message}`);
                }
            };
        }
        
        // Process pending ICE candidates
        function processPendingCandidates() {
            log(`Processing ${pendingCandidates.length} pending candidates`);
            for (const candidate of pendingCandidates) {
                peerConnection.addIceCandidate(new RTCIceCandidate(candidate))
                    .catch(error => log(`Error adding queued candidate: ${error.message}`));
            }
            pendingCandidates = [];
        }
        
        // Socket event handlers with better error handling
        socket.on("connect", () => {
            log("Connected to signaling server");
            connectionStatus.textContent = "Connected to server";
            connectionStatus.style.color = '#2ed573';
            playerIdSpan.textContent = myId;
        });
        
        socket.on("disconnect", (reason) => {
            log(`Disconnected from signaling server: ${reason}`);
            connectionStatus.textContent = `Disconnected: ${reason}`;
            connectionStatus.style.color = '#ff6b6b';
        });
        
        socket.on("connect_error", (error) => {
            log(`Connection error: ${error.message}`);
            connectionStatus.textContent = `Connection error: ${error.message}`;
            connectionStatus.style.color = '#ff6b6b';
        });
        
        socket.on("offer", async (data) => {
            if (data.id === myId) {
                log("Ignoring own offer");
                return;
            }
            
            log(`Received offer from: ${data.id}`);
            try {
                // Make sure we have a peer connection
                if (!peerConnection) {
                    log("No peer connection - creating one to handle offer");
                    createPeerConnection();
                }
                
                isHost = false;
                
                log("Setting remote description");
                await peerConnection.setRemoteDescription(new RTCSessionDescription(data.offer));
                
                // Process any pending candidates now that we have remote description
                processPendingCandidates();
                
                log("Creating answer");
                const answer = await peerConnection.createAnswer();
                await peerConnection.setLocalDescription(answer);
                
                log("Sending answer");
                socket.emit("answer", { 
                    id: myId, 
                    target_id: data.id,
                    answer: answer 
                });
                
                gameStatus.textContent = "Joining game...";
                startBtn.disabled = true;
                joinBtn.disabled = true;
            } catch (error) {
                log(`Error handling offer: ${error.message}`);
                gameStatus.textContent = "Error joining game";
                startBtn.disabled = false;
                joinBtn.disabled = false;
            }
        });
        
        socket.on("answer", async (data) => {
            if (data.id === myId || data.target_id !== myId) {
                log("Ignoring answer - not for us");
                return;
            }
            
            log(`Received answer from: ${data.id}`);
            try {
                log("Setting remote description with answer");
                await peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
                
                // Process any pending candidates now that we have remote description
                processPendingCandidates();
                
                gameStatus.textContent = "Connection established! Waiting for data channel...";
            } catch (error) {
                log(`Error handling answer: ${error.message}`);
                gameStatus.textContent = "Error establishing connection";
            }
        });
        
        socket.on("candidate", async (data) => {
            if (data.id === myId) {
                log("Ignoring own candidate");
                return;
            }
            
            log("Received ICE candidate");
            try {
                if (peerConnection && peerConnection.remoteDescription) {
                    await peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
                    log("Added ICE candidate");
                } else {
                    log("Queuing ICE candidate - remote description not ready");
                    pendingCandidates.push(data.candidate);
                }
            } catch (error) {
                log(`ICE candidate error: ${error.message}`);
            }
        });
        
        // Initialize the game
        initializeBoard();
        updateGameStatus();
        log("Game initialized");
    </script>
</body>
</html>
'''

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/status")
def status():
    return f"Signaling server running. Connected clients: {len(clients)}"

@app.route("/health")
def health():
    return {"status": "healthy", "clients": len(clients)}

@socketio.on("connect")
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    emit("connected", {"sid": request.sid})

@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")
    # Clean up client data
    for client_id, sid in list(clients.items()):
        if sid == request.sid:
            del clients[client_id]
            break

@socketio.on("offer")
def handle_offer(data):
    logger.info(f"Received offer from {data['id']}")
    clients[data["id"]] = request.sid
    # Send offer to all other clients except sender
    emit("offer", data, broadcast=True, include_self=False)

@socketio.on("answer")
def handle_answer(data):
    logger.info(f"Received answer from {data['id']} for target {data.get('target_id', 'unknown')}")
    # Send answer to the specific target client
    target_id = data.get('target_id')
    if target_id and target_id in clients:
        emit("answer", data, room=clients[target_id])
    else:
        # Fallback: broadcast to all except sender
        emit("answer", data, broadcast=True, include_self=False)

@socketio.on("candidate")
def handle_candidate(data):
    logger.info(f"Received ICE candidate from {data.get('id', 'unknown')}")
    # Send candidate to all other clients except sender
    emit("candidate", data, broadcast=True, include_self=False)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting signaling server on port {port}")
    print("For local access: http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=port, debug=False)