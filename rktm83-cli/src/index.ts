#!/usr/bin/env node
import { Command } from 'commander';
import chalk from 'chalk';
import inquirer from 'inquirer';
import { spawn } from 'child_process';
import * as path from 'path';

const program = new Command();

const RKTM83_PATH = path.join(__dirname, '..');

function log(message: string, type: 'info' | 'success' | 'error' = 'info') {
  const colors = {
    info: chalk.blue,
    success: chalk.green,
    error: chalk.red
  };
  console.log(colors[type](message));
}

function runPython(script: string, args: string[] = []): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn('python', [script, ...args], {
      cwd: RKTM83_PATH,
      shell: true
    });
    
    let output = '';
    proc.stdout.on('data', (data) => {
      output += data.toString();
    });
    proc.stderr.on('data', (data) => {
      output += data.toString();
    });
    proc.on('close', (code) => {
      resolve(output);
    });
    proc.on('error', (err) => {
      reject(err);
    });
  });
}

program
  .name('rktm83')
  .description('RKTM83 - Personal AI Agent CLI')
  .version('1.0.0');

program
  .command('chat')
  .description('Chat with the AI agent')
  .argument('[message]', 'Message to send')
  .action(async (message) => {
    if (!message) {
      const answers = await inquirer.prompt([
        {
          type: 'input',
          name: 'message',
          message: 'Enter your message:',
          validate: (input: string) => input.trim().length > 0 || 'Please enter a message'
        }
      ]);
      message = answers.message;
    }
    
    log('Sending to agent...', 'info');
    try {
      const response = await runPython('rktm83-cli/agent.py', ['chat', message]);
      console.log('\n' + chalk.cyan('🤖 RKTM83:') + ' ' + response.trim());
    } catch (err) {
      log(`Error: ${err}`, 'error');
    }
  });

program
  .command('browse')
  .description('Open a website in the browser')
  .argument('<url>', 'Website URL to open')
  .action(async (url) => {
    if (!url.startsWith('http')) {
      url = 'https://' + url;
    }
    log(`Opening ${url}...`, 'info');
    try {
      const response = await runPython('rktm83-cli/agent.py', ['browse', url]);
      console.log('\n' + chalk.cyan('🌐 Result:') + ' ' + response.trim());
    } catch (err) {
      log(`Error: ${err}`, 'error');
    }
  });

program
  .command('search')
  .description('Search the web')
  .argument('<query>', 'Search query')
  .action(async (query) => {
    log(`Searching for "${query}"...`, 'info');
    try {
      const response = await runPython('rktm83-cli/agent.py', ['search', query]);
      console.log('\n' + response.trim());
    } catch (err) {
      log(`Error: ${err}`, 'error');
    }
  });

program
  .command('status')
  .description('Show agent status')
  .action(async () => {
    console.log(chalk.bold('\n╔════════════════════════════════════╗'));
    console.log(chalk.bold('║  🤖 RKTM83 - Agent Status           ║'));
    console.log(chalk.bold('╚════════════════════════════════════╝\n'));
    
    try {
      const response = await runPython('rktm83-cli/agent.py', ['status']);
      console.log(response);
    } catch (err) {
      log(`Error: ${err}`, 'error');
    }
  });

program
  .command('tools')
  .description('List available tools')
  .action(async () => {
    console.log(chalk.bold('\n📦 Available Tools:\n'));
    
    const tools = [
      { name: 'chat', desc: 'Chat with the agent' },
      { name: 'browse', desc: 'Open websites' },
      { name: 'search', desc: 'Web search' },
      { name: 'browse_url', desc: 'Open URL in browser' },
      { name: 'fill_form', desc: 'Fill web forms' },
      { name: 'click_element', desc: 'Click on page elements' },
      { name: 'screenshot', desc: 'Take page screenshot' },
      { name: 'list_files', desc: 'List files in directory' },
      { name: 'read_file', desc: 'Read file content' },
      { name: 'send_email', desc: 'Send emails' },
      { name: 'search_opportunities', desc: 'Find job opportunities' },
      { name: 'find_papers', desc: 'Search academic papers' },
      { name: 'find_issues', desc: 'Find GitHub issues' }
    ];
    
    tools.forEach(tool => {
      console.log(chalk.cyan(`  ${tool.name.padEnd(20)}`) + chalk.gray('- ') + tool.desc);
    });
    console.log('');
  });

program
  .command('run')
  .description('Start interactive chat mode')
  .action(async () => {
    console.log(chalk.bold('\n🎯 RKTM83 Interactive Mode'));
    console.log(chalk.gray('Type your messages. Press Ctrl+C to exit.\n'));
    
    while (true) {
      const answers = await inquirer.prompt([
        {
          type: 'input',
          name: 'message',
          message: chalk.yellow('➜ ')
        }
      ]);
      
      if (answers.message.toLowerCase() === 'exit' || answers.message.toLowerCase() === 'quit') {
        console.log(chalk.green('\nGoodbye! 👋\n'));
        break;
      }
      
      try {
        const response = await runPython('rktm83-cli/agent.py', ['chat', answers.message]);
        console.log(chalk.cyan('\n🤖 ') + response.trim() + '\n');
      } catch (err) {
        log(`Error: ${err}`, 'error');
      }
    }
  });

program
  .command('exec')
  .description('Execute a specific tool directly')
  .argument('<tool>', 'Tool name')
  .argument('[params...]', 'Tool parameters as key=value')
  .action(async (tool, params) => {
    log(`Executing ${tool}...`, 'info');
    try {
      const response = await runPython('rktm83-cli/agent.py', ['exec', tool, ...params]);
      console.log('\n' + response.trim());
    } catch (err) {
      log(`Error: ${err}`, 'error');
    }
  });

program.parse();