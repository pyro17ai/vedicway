import { binaryInfo, ensureBinary } from 'cloakbrowser';

await ensureBinary();
process.stdout.write(`${JSON.stringify(binaryInfo())}\n`);
