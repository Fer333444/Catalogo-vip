self.addEventListener('push', function(event) {
    let data = { title: "Nuevo Contenido", body: "¡Entra a verlo!", url: "/" };
    
    if (event.data) {
        data = event.data.json();
    }
    
    const options = {
        body: data.body,
        icon: 'https://cdn-icons-png.flaticon.com/512/3172/3172558.png', // Un ícono genérico de fuego
        vibrate: [200, 100, 200], // Hace vibrar el celular
        data: { url: data.url }
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// Esto hace que si tocan la notificación, se abra tu página
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});