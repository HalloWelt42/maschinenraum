import '@fontsource/barlow/400.css';
import '@fontsource/barlow/500.css';
import '@fontsource/barlow/600.css';
import '@fontsource/barlow/700.css';
import '@fontsource/chakra-petch/400.css';
import '@fontsource/chakra-petch/500.css';
import '@fontsource/chakra-petch/600.css';
import '@fontsource/chakra-petch/700.css';
import '@fortawesome/fontawesome-free/css/all.min.css';
import './stil/stil.css';
import './stil/farben.css';
import './stil/app.css';
import { mount } from 'svelte';
import App from './App.svelte';
import { ansichtAnwenden } from './lib/ansicht.svelte';

ansichtAnwenden();
mount(App, { target: document.getElementById('app')! });
