import asyncio
from app.services.twitter_playwright import TwitterPlaywrightScraper

async def main():
    print('Iniciando extracción de tweets específica para KarinHerreraVP')
    scraper = TwitterPlaywrightScraper()
    async with scraper:
        # Verificar autenticación
        print('Verificando autenticación')
        auth_status = await scraper.verify_auth()
        print(f'Estado de autenticación: {auth_status}')
        
        print('Extrayendo tweets usando una URL específica con f=live')
        # Directamente usar la URL con f=live para asegurar tweets recientes
        await scraper.page.goto('https://twitter.com/search?q=from%3AKarinHerreraVP&src=typed_query&f=live')
        await asyncio.sleep(8)  # Esperar carga
        
        # Tomar captura para diagnóstico
        await scraper.page.screenshot(path='/tmp/direct_search.png')
        
        # Scrollear para cargar más tweets
        print('Scrolleando para cargar más tweets')
        for i in range(5):
            print(f'Scroll {i+1}/5')
            await scraper.page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(3)
        
        # Extraer tweets
        print('Extrayendo tweets')
        tweets_data = await scraper._extract_tweets_data()
        print(f'Tweets encontrados: {len(tweets_data)}')
        
        # Mostrar tweets
        for i, tweet in enumerate(tweets_data):
            print(f'--- Tweet {i+1} ---')
            print(f'Texto: {tweet.get("texto", "N/A")[:50]}...')
            print(f'Fecha: {tweet.get("timestamp", "N/A")}')
            print()

if __name__ == '__main__':
    asyncio.run(main()) 