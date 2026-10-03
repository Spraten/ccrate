//! Narrow adapter: probe loaded material or print one exact grayscale raster.
use std::{error::Error,io::{self,Read}};
use supvan_proto::{printer::Printer,buffer::Density,dither::DitherMode};
#[tokio::main]
async fn main()->Result<(),Box<dyn Error>>{
 let args:Vec<String>=std::env::args().collect();
 if args.len()<3{return Err("usage: kiosk-label probe|print /dev/hidrawN [width height]".into())}
 let printer=Printer::open_target(&args[2]).await?;
 if !printer.check_device().await?{return Err("Printer did not identify itself".into())}
 let material=printer.query_material().await?.ok_or("Loaded label stock cannot be read")?;
 let status=printer.query_status().await?.ok_or("Printer status cannot be read")?;
 if status.has_error(){return Err(format!("Printer: {}",status.error_description().unwrap_or("Unknown printer error".into())).into())}
 if args[1]=="probe"{println!("{{\"width_mm\":{},\"height_mm\":{},\"gap_mm\":{},\"label_type\":{}}}",material.width_mm,material.height_mm,material.gap_mm,material.label_type);return Ok(())}
 if args[1]!="print"||args.len()!=5{return Err("Invalid command".into())}
 let width:u32=args[3].parse()?;let height:u32=args[4].parse()?;
 if width==0||height<32||width>384||width>material.width_mm as u32*8||height+16>material.height_mm as u32*8{return Err("Raster does not fit the loaded label stock".into())}
 let mut bytes=Vec::new();io::stdin().take((width*height+1) as u64).read_to_end(&mut bytes)?;
 if bytes.len()!=(width*height) as usize{return Err("Raster length does not match dimensions".into())}
 printer.print_grayscale(&bytes,width,height,Density::uniform(4),DitherMode::Bayer).await?;
 println!("{{\"status\":\"printed\"}}");Ok(())
}
