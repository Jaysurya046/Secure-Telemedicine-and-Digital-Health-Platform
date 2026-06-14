export function registerWebRtcSignaling(socket, io) {
  socket.on('webrtc:offer', ({ roomId, offer }) => {
    socket.to(roomId).emit('webrtc:offer', { offer, from: socket.user });
  });

  socket.on('webrtc:answer', ({ roomId, answer }) => {
    socket.to(roomId).emit('webrtc:answer', { answer, from: socket.user });
  });

  socket.on('webrtc:ice-candidate', ({ roomId, candidate }) => {
    socket.to(roomId).emit('webrtc:ice-candidate', { candidate, from: socket.user });
  });

  socket.on('consultation:end-call', ({ roomId }) => {
    io.to(roomId).emit('consultation:call-ended', { endedBy: socket.user });
  });
}
